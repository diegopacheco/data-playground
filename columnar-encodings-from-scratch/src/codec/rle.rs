use super::{Encoded, Item};
use crate::bits::{put_varint, Reader, Res};

pub fn encode<T: Item>(x: &[T]) -> Encoded {
    let mut out = Vec::new();
    put_varint(&mut out, x.len() as u64);
    let mut runs = 0usize;
    let mut i = 0;
    while i < x.len() {
        let mut j = i + 1;
        while j < x.len() && x[j] == x[i] {
            j += 1;
        }
        put_varint(&mut out, (j - i) as u64);
        x[i].put(&mut out);
        runs += 1;
        i = j;
    }
    let avg = if runs == 0 { 0.0 } else { x.len() as f64 / runs as f64 };
    Encoded { bytes: out, detail: format!("{} runs, average run length {:.1}", runs, avg) }
}

pub fn decode<T: Item>(r: &mut Reader) -> Res<Vec<T>> {
    let n = r.len()?;
    let mut out = Vec::with_capacity(n);
    while out.len() < n {
        let run = r.varint()? as usize;
        if run == 0 || run > n - out.len() {
            return Err("bad run length".into());
        }
        let v = T::get(r)?;
        out.extend(std::iter::repeat_n(v, run));
    }
    Ok(out)
}
