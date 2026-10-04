use super::frame::{avg_width, get_block, put_block};
use super::Encoded;
use crate::bits::{put_ivarint, put_varint, Reader, Res};

const BLOCK: usize = 128;

pub fn encode(x: &[i64]) -> Encoded {
    let mut out = Vec::new();
    put_varint(&mut out, x.len() as u64);
    if x.is_empty() {
        return Encoded { bytes: out, detail: "empty".into() };
    }
    put_ivarint(&mut out, x[0]);
    let deltas: Vec<i64> = x.windows(2).map(|w| w[1].wrapping_sub(w[0])).collect();
    let widths: Vec<u32> = deltas.chunks(BLOCK).map(|b| put_block(b, &mut out)).collect();
    Encoded {
        bytes: out,
        detail: format!("first value + differences, blocks of {} deltas with min delta and bit-packed offsets, {}", BLOCK, avg_width(&widths)),
    }
}

pub fn decode(r: &mut Reader) -> Res<Vec<i64>> {
    let n = r.len()?;
    if n == 0 {
        return Ok(Vec::new());
    }
    let first = r.ivarint()?;
    let mut deltas = Vec::with_capacity(n - 1);
    while deltas.len() < n - 1 {
        get_block(r, BLOCK.min(n - 1 - deltas.len()), &mut deltas)?;
    }
    let mut out = Vec::with_capacity(n);
    let mut cur = first;
    out.push(cur);
    for d in deltas {
        cur = cur.wrapping_add(d);
        out.push(cur);
    }
    Ok(out)
}
