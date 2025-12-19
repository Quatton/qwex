use clap::{Parser, Subcommand};
use std::env;
use std::path::PathBuf;

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
    },
    /// Run the project (defaults to ./qwex.yaml)
    Run {
        /// Path to qwex.yaml
        #[arg(value_name = "FILE", default_value = "./qwex.yaml")]
        file: PathBuf,
    },
}

fn main() -> anyhow::Result<()> {
    let cli = Cli::parse();

    let qwex_dir: PathBuf = match cli.qwex_home {
        Some(p) => p,
        None => env::current_dir()?.join(".qwex"),
    };

    match cli.command {
        Some(Commands::Build { o }) => {
            let out = o.unwrap_or_else(|| PathBuf::from("./build-output"));
            build(&qwex_dir, &out)?;
        }
        Some(Commands::Run { file }) => {
            run(&qwex_dir, &file)?;
        }
        None => {
            let default = PathBuf::from("./qwex.yaml");
            run(&qwex_dir, &default)?;
        }
    }

    Ok(())
}

fn build(qwex_dir: &PathBuf, target: &PathBuf) -> anyhow::Result<()> {
    println!(
        "qwex: build (dir={}) -> {}",
        qwex_dir.display(),
        target.display()
    );
    // TODO: implement real build logic
    Ok(())
}

fn run(qwex_dir: &PathBuf, file: &PathBuf) -> anyhow::Result<()> {
    println!(
        "qwex: run (dir={}) -> {}",
        qwex_dir.display(),
        file.display()
    );
    // TODO: implement run logic (use qwex_dir for state/config, parse file, execute, etc.)
    Ok(())
}
