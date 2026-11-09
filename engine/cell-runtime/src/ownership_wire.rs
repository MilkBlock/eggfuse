//! Versioned artifact addresses. Legacy program IDs distinguished source union
//! operands; current IDs describe only local Cell wiring. Neither format stores
//! another union instruction in the runtime port plan.
use super::*;

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub(super) enum Format { Legacy, #[default] Cell }
impl Format {
    pub fn marker_schema(self) -> &'static str {
        match self { Self::Legacy => "eggfuse-ownership-markers/v4", Self::Cell => "eggfuse-ownership-markers/v5" }
    }
    pub fn fragment_schema(self) -> &'static str {
        match self { Self::Legacy => "eggfuse-ownership-fragments/v1", Self::Cell => "eggfuse-ownership-fragments/v2" }
    }
    pub fn profile_schema(self) -> &'static str {
        match self { Self::Legacy => "eggfuse-ownership-fragment-profile/v1", Self::Cell => "eggfuse-ownership-fragment-profile/v2" }
    }
    pub fn profile(raw: &J) -> Result<Self> {
        [Self::Legacy, Self::Cell].into_iter().find(|v| raw["schema"] == v.profile_schema())
            .ok_or("invalid ownership fragment profile".into())
    }
    pub fn program(p: &Program) -> Result<Self> {
        let mut selected = None;
        for (key, marker) in [("ownership_markers", true), ("ownership_fragments", false)] {
            if let Some(raw) = p.artifact.get(key) {
                let version = [Self::Legacy, Self::Cell].into_iter().find(|v|
                    raw["schema"] == if marker { v.marker_schema() } else { v.fragment_schema() })
                    .ok_or("unknown ownership artifact schema")?;
                if selected.is_some_and(|old| old != version) {
                    return Err("ownership marker/fragment address versions differ".into());
                }
                selected = Some(version);
            }
        }
        Ok(selected.unwrap_or_default())
    }
}

/// Temporary borrowed discriminator for old artifacts. New plans do not create
/// it. Original Cell operations remain the sole owners of these operands.
pub(super) fn unions(template: &Template) -> Vec<Option<[&Arg; 2]>> {
    template.ops.iter().map(|op| match op { Op::Union(a, b) => Some([a, b]), _ => None }).collect()
}

pub(super) fn plan(plan: &Plan, p: &Program) -> J {
    let mut raw = json!(plan);
    let mut seen = vec![false; plan.programs.len()];
    for (i, (marker, template)) in plan.markers.iter().zip(&p.templates).enumerate() {
        // Preserve the checked artifact projection without retaining duplicate
        // per-template coverage arrays in the executable plan.
        raw["markers"][i]["active"] = json!(marker.program.active());
        raw["markers"][i]["bodies"] = json!(marker.program.fields.iter()
            .map(|fields| !fields.is_empty()).collect::<Vec<_>>());
        if plan.format == Format::Legacy {
            raw["markers"][i]["unions"] = json!(template.ops.iter().enumerate()
                .filter_map(|(i, op)| matches!(op, Op::Union(..)).then_some(i)).collect::<Vec<_>>());
            if !seen[marker.program_id] {
                seen[marker.program_id] = true;
                raw["programs"][marker.program_id]["unions"] = json!(unions(template));
            }
        }
    }
    raw
}
