# Twin-spec migrations

This document defines the compatibility contract for behavioral twin specs.
The renderer applies these migrations in order before it validates content.

## Current version

The current twin-spec version is `v0.4`. Every generated spec has a
`$schema_version` string in the exact `vMAJOR.MINOR` format. The extractor
stamps `v0.4` onto model and mock responses before validation, even when a
response omits the field or supplies an older value.

Supported versions are:

- `v0.3`: the historical shape described below. It is migrated to `v0.4`.
- `v0.4`: the current shape. It is validated without a compatibility
  backfill.

An explicit version that is not listed above is unsupported. Synthesis fails
closed for that input and writes a degraded twin rather than treating unknown
content as current. The diagnostic points back to this document.

## Historical shapes

### v0.3

The v0.3 shape contained the operational sections: identity, operating model,
decision policy, delegation policy, workflow policy, verification policy,
recovery policy, voice policy, project routing, never and always rules,
examples, and evidence. It did not contain the constitution,
substitution_contract, trust_policy, or agent_supervision_policy sections.

An object without `$schema_version` is accepted as v0.3 only when it has that
legacy shape. The ordered migration derives the four missing sections from
the legacy fields, marks the result `v0.4`, and retains compatibility-default
evidence in the rendered status. This path exists for specs written before
version stamping was introduced.

### v0.4

The v0.4 shape adds the four substitution-contract sections and the required
version discriminator. The schema remains the source of truth for required
fields and nested content types. A malformed v0.4 object is not silently
converted to an older shape.

## Renderer guarantees

Before rendering, synthesis:

1. Classifies the input version or recognizes the bounded unversioned v0.3
   compatibility shape.
2. Applies the ordered migration chain.
3. Validates the migrated object against `twin-spec-schema.json`.
4. Renders only validated current content, or an explicitly degraded twin.

An unknown explicit version never receives current-version defaults or
user-substitution authority. Validation diagnostics retain JSON field paths
and identify the expected `$schema_version` (`v0.4`). The historical path
renders a visible `v0.3 → v0.4 compatibility` status.

## Strict substitution

`--strict-substitution` applies within the historical v0.3 compatibility path.
When enabled, synthesis does not derive missing substitution sections from
legacy fields. It emits a degraded twin instead. The flag does not bypass
version checks and does not weaken v0.4 schema validation.
