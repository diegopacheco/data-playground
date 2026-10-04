use super::Encoded;
use crate::bits::{pack, put_ivarint, put_varint, unpack, width, Reader, Res};

pub const BLOCK: usize = 1024;

pub fn put_block(block: &[i64], out: &mut Vec<u8>) -> u32 {
    let min = block.iter().copied().min().unwrap_or(0);
    let offs: Vec<u64> = block.iter().map(|v| (*v as i128 - min as i128) as u64).collect();
    let w = width(offs.iter().copied().max().unwrap_or(0));
    put_ivarint(out, min);
    out.push(w as u8);
    pack(&offs, w, out);
    w
}

pub fn get_block(r: &mut Reader, count: usize, out: &mut Vec<i64>) -> Res<()> {
    let min = r.ivarint()?;
    let w = r.u8()? as u32;
    out.extend(unpack(r, count, w)?.into_iter().map(|o| min.wrapping_add(o as i64)));
    Ok(())
}

pub fn encode(x: &[i64]) -> Encoded {
    let mut out = Vec::new();
    put_varint(&mut out, x.len() as u64);
    let widths: Vec<u32> = x.chunks(BLOCK).map(|b| put_block(b, &mut out)).collect();
    Encoded { bytes: out, detail: format!("blocks of {}: min stored once, offsets bit-packed, {}", BLOCK, avg_width(&widths)) }
}

pub fn decode(r: &mut Reader) -> Res<Vec<i64>> {
    let n = r.len()?;
    let mut out = Vec::with_capacity(n);
    while out.len() < n {
        get_block(r, BLOCK.min(n - out.len()), &mut out)?;
    }
    Ok(out)
}

pub fn avg_width(widths: &[u32]) -> String {
    if widths.is_empty() {
        return "no blocks".into();
    }
    let avg = widths.iter().sum::<u32>() as f64 / widths.len() as f64;
    format!("average width {:.1} bits (min {}, max {})", avg, widths.iter().min().unwrap(), widths.iter().max().unwrap())
}
