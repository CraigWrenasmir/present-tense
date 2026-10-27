# World map provenance

`world.json` contains 15,495 land points derived from **Natural Earth 1:110m land**, version 4.0.0. The downloaded source contains 127 polygon records. No coastlines were hand-drawn.

- Dataset: <https://www.naturalearthdata.com/downloads/110m-physical-vectors/110m-land/>
- Original ZIP: <https://naturalearth.s3.amazonaws.com/110m_physical/ne_110m_land.zip>
- Terms: <https://www.naturalearthdata.com/about/terms-of-use/>
- Licence: public domain. Natural Earth permits modification and redistribution, including commercial use.
- Download checked: 27 October 2026.
- Original ZIP SHA-256: `1926c621afd6ac67c3f36639bb1236134a48d82226dc675d3e3df53d02d2a3de`.

## Derivation and coordinates

The asset samples the centres of a 360-column × 145-row equirectangular grid (one degree) against the source land polygons, respecting polygon rings. An earlier build used a 144 × 58 grid; the finer grid was regenerated on 27 October 2026 so the continents read as shapes at the smallest zoom. Coordinates are `[longitude, latitude]` in degrees. Longitude spans −180° to 180°; the viewport spans −60° to 85° latitude. Antarctica is outside the viewport. Small islands and coastline detail may disappear at this scale.

Render using:

```js
const x = (longitude + 180) / 360 * width;
const y = (85 - latitude) / 145 * height;
```

To retain the intended geographic proportions, use a viewport width-to-height ratio of `360 / 145` (approximately 2.48). Typography can make an ASCII rendering appear slightly different even when point coordinates are accurate.

The map encodes **land only**. It contains no country borders, national claims, article geocoding or population data. The application’s publisher markers are a separate layer and should be labelled as publisher origin, not event location. Source-count markers describe the collected dataset, not a country’s volume of news or public opinion.

Validation: unique points; all coordinates within the documented bounds; a compact asset under 400 KB; an inspected text rendering showing recognisable continents and major islands.
