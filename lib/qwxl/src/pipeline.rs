use std::path::PathBuf;

mod ast;
mod error;
mod parser;

struct Config {
    home_dir: PathBuf,
}
