// ---- STEP D, stage 2 of 2: run AFTER stage1_classmap.js's task 'banni_rf_classmap_2023' has finished.
// This is step D of banni_rf.js with two changes, both needed for the export to run at all:
//  1. map23 is read from the stored class map instead of being recomputed by the random forest in every request.
//  2. tileScale: 16 on the two MODIS reduceRegion calls. MODIS's sinusoidal pixels are strongly slanted at 69 E, so one
//     request over the ROI needs a ~146 km wide block of the 10 m map ("Reprojection output too large (14637x5634 pixels)");
//     tileScale splits each reduction into smaller tiles. It changes how the work is split, not the result.
// Thresholds (Prosopis share > 0.4 / < 0.05, water share < 0.1), MODIS QA rule, CHIRPS sum and scales are unchanged.
var roi = ee.Geometry.Rectangle([69.0, 23.4, 69.9, 23.9]);
Map.centerObject(roi, 10);
var map23 = ee.Image('projects/banni-trend-2026/assets/banni_rf_classmap_2023').select('classification');
var pal = ['d73027', 'fdae61', '4575b4', 'fee08b'];
Map.addLayer(map23, {min: 1, max: 4, palette: pal}, 'RF 2023 (stored)');

var modis = ee.ImageCollection('MODIS/061/MOD13Q1');
var mproj = ee.Image(modis.first()).select('NDVI').projection();
var frac = map23.eq(1).reduceResolution({reducer: ee.Reducer.mean(), maxPixels: 1024}).reproject(mproj);
var wfrac = map23.eq(3).reduceResolution({reducer: ee.Reducer.mean(), maxPixels: 1024}).reproject(mproj);
var hi = frac.gt(0.4).and(wfrac.lt(0.1));
var lo = frac.lt(0.05).and(wfrac.lt(0.1));
Map.addLayer(hi.selfMask(), {palette: ['red']}, 'MODIS pixels: high Prosopis', false);
Map.addLayer(lo.selfMask(), {palette: ['green']}, 'MODIS pixels: low Prosopis', false);

var years = ee.List.sequence(2001, 2024);
var out = ee.FeatureCollection(years.map(function (y) {
  y = ee.Number(y);
  var col = modis.filterDate(ee.Date.fromYMD(y, 6, 1), ee.Date.fromYMD(y, 10, 1))
    .map(function (i) { return i.updateMask(i.select('SummaryQA').lte(1)); });
  var nd = col.select('NDVI').mean().multiply(0.0001);
  var mHi = nd.updateMask(hi).reduceRegion({reducer: ee.Reducer.mean(), geometry: roi, scale: 250, maxPixels: 1e9, tileScale: 16});
  var mLo = nd.updateMask(lo).reduceRegion({reducer: ee.Reducer.mean(), geometry: roi, scale: 250, maxPixels: 1e9, tileScale: 16});
  var rain = ee.ImageCollection('UCSB-CHG/CHIRPS/DAILY')
    .filterDate(ee.Date.fromYMD(y, 6, 1), ee.Date.fromYMD(y, 10, 1)).sum()
    .reduceRegion({reducer: ee.Reducer.mean(), geometry: roi, scale: 5566, maxPixels: 1e9});
  return ee.Feature(null, {
    year: y,
    ndvi_hi_pros: mHi.get('NDVI'),
    ndvi_lo_pros: mLo.get('NDVI'),
    chirps_monsoon_mm: rain.get('precipitation')
  });
}));
print('Preview', out.limit(5));
Export.table.toDrive({collection: out, description: 'banni_ndvi_by_prosopis_chirps', fileFormat: 'CSV'});
