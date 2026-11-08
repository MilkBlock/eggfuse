use serde_json::Value;
use sha2::{Digest, Sha256};
pub fn digest(value: &Value) -> String {
    format!(
        "{:x}",
        Sha256::digest(serde_json::to_vec(value).expect("JSON value serialization"))
    )
}

#[cfg(test)]
mod tests {
    #[test]
    fn diagnostic_times_survive_checkpoint_roundtrip() {
        let value =
            serde_json::json!({"match_seconds":3.3300000000000003e-7,"entry_seconds":2.08e-7});
        let bytes = serde_json::to_vec(&value).unwrap();
        let restored: serde_json::Value = serde_json::from_slice(&bytes).unwrap();
        assert_eq!(super::digest(&value), super::digest(&restored));
    }
}

/// Stable JSON used by the Recipe and Cell artifact formats. Native frontends
/// may enable serde_json's preserve_order feature through Cargo unification.
pub fn canonical(value: &Value, spaced: bool) -> String {
    let mut sorted = value.clone();
    sorted.sort_all_objects();
    let mut out = String::new();
    let mut quoted = false;
    let mut escaped = false;
    for c in sorted.to_string().chars() {
        if !c.is_ascii() || c == '\u{7f}' {
            use std::fmt::Write;
            for unit in c.encode_utf16(&mut [0; 2]) {
                write!(out, "\\u{unit:04x}").unwrap();
            }
        } else {
            out.push(c);
        }
        if quoted {
            if !escaped && c == '"' {
                quoted = false;
            }
            escaped = !escaped && c == '\\';
        } else if c == '"' {
            quoted = true;
        } else if spaced && matches!(c, ':' | ',') {
            out.push(' ');
        }
    }
    out
}
pub fn artifact_digest(value: &Value) -> String {
    artifact_digest_excluding_root(value, &[])
}

/// Canonical hashing without cloning the JSON tree. Omissions apply only at
/// the root, so a profile can fingerprint its source without copying it twice.
pub fn artifact_digest_excluding_root(value: &Value, omit: &[&str]) -> String {
    use serde::ser::{Serialize, SerializeMap, SerializeSeq, Serializer};
    struct Borrowed<'a> {
        value: &'a Value,
        omit: &'a [&'a str],
    }
    impl Serialize for Borrowed<'_> {
        fn serialize<S: Serializer>(&self, serializer: S) -> Result<S::Ok, S::Error> {
            match self.value {
                Value::Object(object) => {
                    let mut entries = object
                        .iter()
                        .filter(|(key, _)| !self.omit.contains(&key.as_str()))
                        .collect::<smallvec::SmallVec<[_; 8]>>();
                    entries.sort_unstable_by(|a, b| a.0.cmp(b.0));
                    let mut out = serializer.serialize_map(Some(entries.len()))?;
                    for (key, value) in entries {
                        out.serialize_entry(key, &Borrowed { value, omit: &[] })?;
                    }
                    out.end()
                }
                Value::Array(items) => {
                    let mut out = serializer.serialize_seq(Some(items.len()))?;
                    for value in items {
                        out.serialize_element(&Borrowed { value, omit: &[] })?;
                    }
                    out.end()
                }
                value => value.serialize(serializer),
            }
        }
    }
    let bytes = serde_json::to_vec(&Borrowed { value, omit }).expect("JSON value serialization");
    if bytes.is_ascii() && !bytes.contains(&0x7f) {
        return format!("{:x}", Sha256::digest(&bytes));
    }
    let mut ascii = String::with_capacity(bytes.len());
    for c in std::str::from_utf8(&bytes).unwrap().chars() {
        if c.is_ascii() && c != '\u{7f}' {
            ascii.push(c);
        } else {
            use std::fmt::Write;
            for unit in c.encode_utf16(&mut [0; 2]) {
                write!(ascii, "\\u{unit:04x}").unwrap();
            }
        }
    }
    format!("{:x}", Sha256::digest(ascii.as_bytes()))
}

#[cfg(test)]
mod canonical_tests {
    use super::*;
    #[test]
    fn borrowed_hash_preserves_the_artifact_format_including_unicode_and_floats() {
        for value in [
            serde_json::json!({"z":[1,-0.0,3.3300000000000003e-7],"a":{"y":true,"b":null}}),
            serde_json::json!({"字":"quote\" slash\\ \n\u{7f}é😀","sha256":"keep"}),
            Value::Object(
                (0..30)
                    .rev()
                    .map(|i| (format!("key{i}"), serde_json::json!([i, "value"])))
                    .collect(),
            ),
        ] {
            assert_eq!(
                artifact_digest(&value),
                format!("{:x}", Sha256::digest(canonical(&value, false).as_bytes()))
            );
        }
    }
    #[test]
    fn source_hash_omits_only_root_metadata() {
        let raw = serde_json::json!({"sha256":"root","ownership_fragments":{},"nested":{"sha256":"keep","ownership_fragments":[1]}});
        let expected = serde_json::json!({"nested":{"sha256":"keep","ownership_fragments":[1]}});
        assert_eq!(
            artifact_digest_excluding_root(&raw, &["sha256", "ownership_fragments"]),
            artifact_digest(&expected)
        );
    }
}
