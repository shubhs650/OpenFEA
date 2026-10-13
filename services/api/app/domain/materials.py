"""Sourced material copies, bounded development policy, and honest prerequisites."""

from datetime import date
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, HttpUrl, ValidationError, model_validator

from app.domain.base import StrictModel
from app.domain.errors import DomainError
from app.domain.units import PresetID, to_si

Text = Annotated[str, Field(min_length=1, max_length=1000)]
Positive = Annotated[float, Field(gt=0, strict=True)]
Poisson = Annotated[float, Field(ge=0, le=0.45, strict=True)]


class MaterialValues(StrictModel):
    young_modulus: Positive
    poisson_ratio: Poisson
    density: Positive | None = None
    yield_strength: Positive | None = None


class SIProperties(StrictModel):
    young_modulus_pa: Positive
    poisson_ratio: Poisson
    density_kg_m3: Positive | None = None
    yield_strength_pa: Positive | None = None


class MaterialSource(StrictModel):
    title: Text
    url: HttpUrl | None = None
    accessed_on: date | None = None


class MaterialProvenance(StrictModel):
    name: Annotated[str, Field(min_length=1, max_length=200)]
    grade: Text
    condition: Text
    temperature_note: Text
    sources: list[MaterialSource] = Field(min_length=1, max_length=5)
    assumptions: Text


class CustomMaterial(StrictModel):
    kind: Literal["custom"]
    units: PresetID
    values: MaterialValues
    provenance: MaterialProvenance
    confirmed: Literal[True]


class SampleMaterial(StrictModel):
    kind: Literal["sample"]
    sample_id: Annotated[str, Field(min_length=1, max_length=100)]
    library_version: Annotated[str, Field(min_length=1, max_length=100)]
    confirmed: Literal[True]


class MaterialAssignment(StrictModel):
    material: Annotated[CustomMaterial | SampleMaterial, Field(discriminator="kind")]


class MaterialSnapshot(StrictModel):
    schema_version: Literal[1] = 1
    kind: Literal["sample", "custom"]
    library_id: str | None = None
    library_version: str | None = None
    properties: SIProperties
    source_units: PresetID
    source_values: MaterialValues
    provenance: MaterialProvenance
    confirmed: Literal[True] = True


class MaterialExample(StrictModel):
    """A library template carries no claim of user confirmation."""

    library_id: str
    library_version: str
    properties: SIProperties
    source_units: PresetID
    source_values: MaterialValues
    provenance: MaterialProvenance


class BodyMaterial(StrictModel):
    body_id: Annotated[str, Field(min_length=1, max_length=200)]
    material: MaterialSnapshot


class MaterialSetup(StrictModel):
    schema_version: Literal[1] = 1
    display_units: PresetID = "mm-N-MPa"
    assignments: list[BodyMaterial] = Field(default_factory=list, max_length=10)

    @model_validator(mode="after")
    def unique_bodies(self) -> "MaterialSetup":
        if len({a.body_id for a in self.assignments}) != len(self.assignments):
            raise ValueError("Each body has at most one material")
        return self


class DisplayUnitsPatch(StrictModel):
    preset: PresetID


class BodyMaterialStatus(StrictModel):
    body_id: str
    material_assigned: bool
    gravity_available: bool
    yield_factor_available: bool
    warnings: list[str]


class MaterialState(StrictModel):
    analysis_id: UUID
    analysis_revision: int
    geometry_revision_id: UUID | None
    setup: MaterialSetup
    bodies: list[BodyMaterialStatus]


LIBRARY_VERSION = "2026-10-13.1"


def custom_snapshot(material: CustomMaterial) -> MaterialSnapshot:
    values = material.values
    try:
        properties = SIProperties(
            young_modulus_pa=to_si(values.young_modulus, material.units, "stress"),
            poisson_ratio=values.poisson_ratio,
            density_kg_m3=to_si(values.density, material.units, "density")
            if values.density is not None
            else None,
            yield_strength_pa=to_si(values.yield_strength, material.units, "stress")
            if values.yield_strength is not None
            else None,
        )
    except (ValueError, ValidationError):
        raise DomainError(
            422, "invalid_material", "Material properties must be positive and finite in SI"
        ) from None
    return MaterialSnapshot(
        kind="custom",
        properties=properties,
        source_units=material.units,
        source_values=values,
        provenance=material.provenance,
    )


def _sample(
    identifier: str, values: MaterialValues, provenance: MaterialProvenance
) -> MaterialSnapshot:
    snapshot = custom_snapshot(
        CustomMaterial(
            kind="custom",
            units="m-N-Pa",
            values=values,
            provenance=provenance,
            confirmed=True,
        )
    )
    return snapshot.model_copy(
        update={"kind": "sample", "library_id": identifier, "library_version": LIBRARY_VERSION}
    )


SAMPLES: dict[str, MaterialSnapshot] = {
    "al-6061-t6-rod": _sample(
        "al-6061-t6-rod",
        MaterialValues(
            young_modulus=68.3e9, poisson_ratio=0.33, density=2700, yield_strength=276e6
        ),
        MaterialProvenance(
            name="Aluminium 6061-T6 rod/bar example",
            grade="6061",
            condition="T6/T651 rod and bar; typical properties",
            temperature_note="Room-temperature example; density reference 20 °C",
            sources=[
                MaterialSource(
                    title="Kaiser Aluminum KA-RBH-6061-8.10, pp. 1–2",
                    url=HttpUrl(
                        "https://online.kaiseraluminum.com/depot/PublicProductInformation/Document/1025/Kaiser_Aluminum_6061_Rod_and_Bar.pdf"
                    ),
                    accessed_on=date(2026, 10, 13),
                )
            ],
            assumptions=(
                "Use the datasheet metric column: E=68.3 GPa, density=2.70 Mg/m³, "
                "typical yield=276 MPa. Poisson ratio 0.33 is an explicit project assumption, "
                "not a sourced measurement. Isotropic approximation; typical values are not "
                "certified allowables. Confirm suitability for your product, "
                "direction and temperature."
            ),
        ),
    ),
    "stainless-304": _sample(
        "stainless-304",
        MaterialValues(young_modulus=200e9, poisson_ratio=0.30, density=7900),
        MaterialProvenance(
            name="Stainless 304/4301 example",
            grade="EN 1.4301 / UNS S30400",
            condition="Core 304/4301; product form unspecified",
            temperature_note="Physical properties at 20 °C",
            sources=[
                MaterialSource(
                    title="Outokumpu Core range datasheet, physical properties p. 10",
                    url=HttpUrl(
                        "https://www.outokumpu.com/-/media/files/products/core/outokumpu-core-range-datasheet.pdf"
                    ),
                    accessed_on=date(2026, 10, 13),
                )
            ],
            assumptions=(
                "E=200 GPa and density=7.9 kg/dm³ from the metric physical-properties table. "
                "Poisson ratio 0.30 is an explicit project assumption. Yield is intentionally "
                "omitted because product form/condition must be specified. "
                "Isotropic room-temperature example, not a certified allowable."
            ),
        ),
    ),
}


def snapshot_for(material: CustomMaterial | SampleMaterial) -> MaterialSnapshot:
    if isinstance(material, CustomMaterial):
        return custom_snapshot(material)
    if material.sample_id not in SAMPLES:
        raise DomainError(
            422, "unknown_material", "Choose an available sample or enter custom properties"
        )
    # Copy all properties/provenance into the revision; never persist a live library lookup.
    if material.library_version != SAMPLES[material.sample_id].library_version:
        raise DomainError(
            409,
            "material_library_changed",
            "The sample library changed. Reload and review the current example before applying it.",
        )
    return SAMPLES[material.sample_id].model_copy(deep=True)


def body_status(body: str, snapshot: MaterialSnapshot | None) -> BodyMaterialStatus:
    warnings = []
    if snapshot is None:
        warnings.append("Assign and confirm a material before meshing or solving.")
    else:
        if snapshot.properties.poisson_ratio >= 0.4:
            warnings.append(
                "High Poisson ratio: displacement tetrahedra may lock. This limited development "
                "range is not broad near-incompressible validation."
            )
        if snapshot.properties.density_kg_m3 is None:
            warnings.append("Gravity unavailable: density is missing.")
        if snapshot.properties.yield_strength_pa is None:
            warnings.append("Yield factor of safety unavailable: yield strength is missing.")
    return BodyMaterialStatus(
        body_id=body,
        material_assigned=snapshot is not None,
        gravity_available=snapshot is not None and snapshot.properties.density_kg_m3 is not None,
        yield_factor_available=snapshot is not None
        and snapshot.properties.yield_strength_pa is not None,
        warnings=warnings,
    )
