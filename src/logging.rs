use std::fs::{self, File, OpenOptions};
use std::io::{self, Write};
use std::path::Path;
use std::sync::{Arc, Mutex, MutexGuard};
use tracing_subscriber::filter::LevelFilter;
use tracing_subscriber::fmt::MakeWriter;
use tracing_subscriber::layer::SubscriberExt;
use tracing_subscriber::util::SubscriberInitExt;
use tracing_subscriber::Layer;

/// A `MakeWriter` that appends to one shared log file, mirroring the Python
/// bot's `logs/positions.log` handler.
#[derive(Clone)]
struct SharedFile(Arc<Mutex<File>>);

struct SharedFileGuard<'a>(MutexGuard<'a, File>);

impl<'a> MakeWriter<'a> for SharedFile {
    type Writer = SharedFileGuard<'a>;

    fn make_writer(&'a self) -> Self::Writer {
        SharedFileGuard(self.0.lock().unwrap_or_else(|poisoned| poisoned.into_inner()))
    }
}

impl Write for SharedFileGuard<'_> {
    fn write(&mut self, buf: &[u8]) -> io::Result<usize> {
        self.0.write(buf)
    }

    fn flush(&mut self) -> io::Result<()> {
        self.0.flush()
    }
}

/// Console at INFO and file at DEBUG, like the original logging setup.
pub fn init(log_path: &str) -> io::Result<()> {
    if let Some(parent) = Path::new(log_path).parent() {
        fs::create_dir_all(parent)?;
    }

    let file = OpenOptions::new()
        .create(true)
        .append(true)
        .open(log_path)?;

    let writer = SharedFile(Arc::new(Mutex::new(file)));

    let console = tracing_subscriber::fmt::layer()
        .with_target(false)
        .with_filter(LevelFilter::INFO);

    let file_layer = tracing_subscriber::fmt::layer()
        .with_target(false)
        .with_ansi(false)
        .with_writer(writer)
        .with_filter(LevelFilter::DEBUG);

    tracing_subscriber::registry()
        .with(console)
        .with(file_layer)
        .with(LevelFilter::DEBUG)
        .init();

    Ok(())
}
