use super::{Encoded, Item};
use crate::bits::{pack, put_varint, unpack, width, Reader, Res};
use std::collections::HashMap;

pub fn encode<T: Item>(x: &[T]) -> Encoded {
    let mut ids: HashMap<&T, u64> = HashMap::new();
    let mut entries: Vec<&T> = Vec::new();
    let codes: Vec<u64> = x
        .iter()
        .map(|v| {
            *ids.entry(v).or_insert_with(|| {
                entries.push(v);
                entries.len() as u64 - 1
            })
        })
        .collect();
    let mut out = Vec::new();
    put_varint(&mut out, x.len() as u64);
    put_varint(&mut out, entries.len() as u64);
    entries.iter().for_each(|e| e.put(&mut out));
    let w = width(entries.len().saturating_sub(1) as u64);
    out.push(w as u8);
    let dict_bytes = out.len();
    pack(&codes, w, &mut out);
    Encoded {
        detail: format!("cardinality {}, dictionary {} bytes, ids bit-packed at {} bits", entries.len(), dict_bytes, w),
        bytes: out,
    }
}

pub fn decode<T: Item>(r: &mut Reader) -> Res<Vec<T>> {
    let n = r.len()?;
    let k = r.len()?;
    let entries: Vec<T> = (0..k).map(|_| T::get(r)).collect::<Res<_>>()?;
    let w = r.u8()? as u32;
    unpack(r, n, w)?
        .into_iter()
        .map(|c| entries.get(c as usize).cloned().ok_or_else(|| "dictionary id out of range".to_string()))
        .collect()
}
