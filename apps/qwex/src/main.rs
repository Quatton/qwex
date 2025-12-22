use clap::{Parser, Subcommand};
use qwxl::pipeline::{Config, Pipeline};
use std::env;
use std::path::PathBuf;
use tracing::debug;
use tracing_subscriber::layer::SubscriberExt as _;
use tracing_subscriber::util::SubscriberInitExt as _;
use tracing_subscriber::{self, fmt};

use tracing_subscriber::filter::EnvFilter;

#[derive(Parser)]
#[command(name = "qwex")]
#[command(about = "qwex CLI", long_about = None)]
struct Cli {
    #[arg(long, global = true, value_name = "PATH")]
    qwex_home: Option<PathBuf>,

    #[command(subcommand)]
    command: Option<Commands>,
}

#[derive(Subcommand)]
enum Commands {
    /// Build the project
    Build {
        /// Output target path
        #[arg(short, long, value_name = "TARGET")]
        o: Option<PathBuf>,

        #[arg(value_name = "FILE")]
        file: PathBuf,
    },
    /// Run the project (defaults to ./qwex.yaml)
    Run {
        /// Path to qwex.yaml
        #[arg(value_name = "FILE")]
        file: PathBuf,
    },
}

fn main() -> anyhow::Result<()> {
    tracing_subscriber::registry()
        .with(fmt::layer())
        .with(EnvFilter::from_default_env())
        .init();

    let cli = Cli::parse();

    let qwex_dir: PathBuf = match cli.qwex_home {
        Some(p) => p,
        None => env::current_dir()?.join(".qwex"),
    };

    let mut config = Config {
        home_dir: qwex_dir,
        ..Default::default()
    };

    match cli.command {
        Some(Commands::Build { o, file }) => {
            if let Some(target) = o {
                config.target_path = target;
            }
            config.source_path = file;
            build(config)?;
        }
        Some(Commands::Run { file }) => {
            config.source_path = file;
            run(config)?;
        }
        None => {
            run(config)?;
        }
    }

    Ok(())
}

fn build(config: Config) -> anyhow::Result<()> {
    let mut pipeline = Pipeline::new(config.clone());
    let script = pipeline.compile()?;
    debug!("Writing script to: {}", config.target_path.display());
    if let Some(parent) = config.target_path.parent() {
        debug!("Creating parent dir: {}", parent.display());
        std::fs::create_dir_all(parent)?;
    }
    std::fs::write(&config.target_path, script)?;
    println!("Built script at {}", config.target_path.display());
    Ok(())
}

fn run(config: Config) -> anyhow::Result<()> {
    build(config.clone())?;
    // Execute the script
    let status = std::process::Command::new("bash")
        .arg(&config.target_path)
        .status()?;
    if !status.success() {
        anyhow::bail!(
            "Script failed with exit code {}",
            status.code().unwrap_or(-1)
        );
    }
    Ok(())
}
