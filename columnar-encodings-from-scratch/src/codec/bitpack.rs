use super::Encoded;
use crate::bits::{pack, put_varint, unpack, unzigzag, width, zigzag, Reader, Res};

pub fn encode(x: &[i64]) -> Encoded {
    let z: Vec<u64> = x.iter().map(|v| zigzag(*v)).collect();
    let w = width(z.iter().copied().max().unwrap_or(0));
    let mut out = Vec::new();
    put_varint(&mut out, x.len() as u64);
    out.push(w as u8);
    pack(&z, w, &mut out);
    Encoded { bytes: out, detail: format!("zigzag then one global width of {} bits for every value", w) }
}

pub fn decode(r: &mut Reader) -> Res<Vec<i64>> {
    let n = r.len()?;
    let w = r.u8()? as u32;
    Ok(unpack(r, n, w)?.into_iter().map(unzigzag).collect())
}
