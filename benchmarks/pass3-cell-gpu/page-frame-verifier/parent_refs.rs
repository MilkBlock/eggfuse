/// Source commits can retain a loan on their original immutable page rather than a private copy.
#[derive(Clone, Debug)]
enum ParentRefs {
    Owned(Vec<Ref>),
    Page(MultiPage, usize),
}
impl std::ops::Deref for ParentRefs {
    type Target = [Ref];
    fn deref(&self) -> &[Ref] {
        match self {
            Self::Owned(v) => v,
            Self::Page(p, i) => p.parents(*i),
        }
    }
}
impl<'a> IntoIterator for &'a ParentRefs {
    type Item = &'a Ref;
    type IntoIter = std::slice::Iter<'a, Ref>;
    fn into_iter(self) -> Self::IntoIter {
        self.iter()
    }
}
impl serde::Serialize for ParentRefs {
    fn serialize<S: serde::Serializer>(
        &self,
        serializer: S,
    ) -> std::result::Result<S::Ok, S::Error> {
        self[..].serialize(serializer)
    }
}
