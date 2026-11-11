//! Sends a heartbeat to the controller every few seconds.
//! Logs: `cluster logs agent -f`

use std::io::{Read, Write};
use std::net::TcpStream;
use std::time::Duration;
use std::{env, thread};

fn main() {
    let controller = arg_value("--controller").unwrap_or_else(|| "localhost:8080".into());
    let node = env::var("NODE_NAME").unwrap_or_else(|_| "unknown".into());
    let secs = env::var("HEARTBEAT_SECS").ok().and_then(|s| s.parse().ok()).unwrap_or(5);
    println!("agent on {node}: reporting to {controller} every {secs}s");

    loop {
        match heartbeat(&controller, &node) {
            Ok(()) => {}
            Err(e) => eprintln!("heartbeat to {controller} failed: {e}"),
        }
        thread::sleep(Duration::from_secs(secs));
    }
}

fn heartbeat(controller: &str, node: &str) -> std::io::Result<()> {
    let mut stream = TcpStream::connect(controller)?;
    stream.set_write_timeout(Some(Duration::from_secs(5)))?;
    stream.set_read_timeout(Some(Duration::from_secs(5)))?;
    write!(
        stream,
        "POST /heartbeat HTTP/1.1\r\nHost: {controller}\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{node}",
        node.len()
    )?;
    let mut response = String::new();
    stream.read_to_string(&mut response)?; // wait for the reply before hanging up
    Ok(())
}

fn arg_value(flag: &str) -> Option<String> {
    let args: Vec<String> = env::args().collect();
    args.iter().position(|a| a == flag).and_then(|i| args.get(i + 1).cloned())
}
