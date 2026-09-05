# Licensing

This repository holds two kinds of work with different obligations, and they are
licensed differently for a reason rather than by preference.

## Code that derives from ns-3

`simulation/cv2xids/` and `docs/patches/nr-sl-rsrp-trace.patch` are an ns-3
contrib module and a patch to the 5G-LENA `nr` module. They include ns-3 headers
and link against it, so they are derivative works of GPL-2.0-only software and
carry the same terms. ns-3 is GPL-2.0-only, and the CTTC `nr` module is
GPL-2.0-only with some MIT and NIST-Software components.

**These are GPL-2.0-only.** The full text is in [`LICENSE`](LICENSE), copied from
the ns-3 distribution this module is built against. Upstream copyright notices
are preserved. There is no choice being exercised here: distributing this code
under weaker terms would not be permitted.

## Everything else

`analysis/` is standalone Python. It reads CSV and pickle files produced by the
simulation and never links ns-3, so it is not a derivative work. It is covered by
`LICENSE` as well, because shipping one repository under one licence is clearer
for anyone trying to reuse it than a per-directory split whose boundary they have
to reason about. If a component is ever needed under weaker terms, lift it into
its own package with its own licence rather than annotating this one.

## Data products

The dataset is **not** in this repository and is not covered by `LICENSE`.
Software licences are the wrong instrument for data. When the corpus, the raw
simulator output and the generator artefact are released, the data records are
intended to be **CC BY 4.0**, which is what VeReMi NextGen uses and what permits
training and redistribution with attribution. The generator artefact carries the
GPL-2.0-only terms above, because it contains the ns-3 module.

Nothing is released yet. Until a record exists with a DOI, this section is a
statement of intent rather than a grant.

## Third-party components

| component | upstream | terms |
|---|---|---|
| ns-3.42 | nsnam.org | GPL-2.0-only |
| 5G-LENA `nr`, tag `v2x-1.1` | CTTC | GPL-2.0-only, with MIT and NIST-Software parts |
| Python analysis dependencies | numpy, pandas, scikit-learn, scipy, matplotlib, torch | their own terms, unmodified and not redistributed here |
