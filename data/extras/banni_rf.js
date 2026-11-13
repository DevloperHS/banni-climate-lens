// Banni Prosopis Random Forest + NDVI trend by Prosopis share  (GEE Code Editor)
// Classes: 1 Prosopis woodland, 2 Mixed (Prosopis+grass), 3 Wetland/water, 4 Saline brushland

var roi = ee.Geometry.Rectangle([69.0, 23.4, 69.9, 23.9]);
Map.centerObject(roi, 10);

// ---- STEP A: training sites from the Zenodo transects (UTM 42N). Dominant class >=65% in 100 m buffer (2023)
var sites = [
  // [name, E, N, class]
  ['LTM_10', 526996.321, 2620503.022, 1],
  ['GORE-PROS', 553000.756, 2626756.504, 1],
  ['LTM_15', 530767.138, 2612165.708, 2],
  ['LTM_18', 530747.459, 2624127.855, 2],
  ['LTM_26', 534745.173, 2624301.172, 2],
  ['LTM_44', 546264.782, 2611981.772, 2],
  ['LTM_29', 538760.270, 2608103.298, 4],
  ['LTM_30', 538757.873, 2612081.015, 4],
  ['LTM_36', 542770.005, 2608165.522, 4],
  ['LTM_43', 546741.904, 2608154.328, 4]
];
var siteFC = ee.FeatureCollection(sites.map(function (s) {
  return ee.Feature(ee.Geometry.Point([s[1], s[2]], 'EPSG:32642').buffer(60), {'class': s[3]});
}));

// ---- STEP B: add YOUR hand-picked points (draw in Map, import as manualPros / manualMix / manualWater / manualBrush)
// Each needs >= 30 points. Delete the lines for a class you did not draw.
var manual = ee.FeatureCollection([]);
if (typeof manualPros !== 'undefined') manual = manual.merge(manualPros.map(function (f) { return f.buffer(20).set('class', 1); }));
if (typeof manualMix !== 'undefined') manual = manual.merge(manualMix.map(function (f) { return f.buffer(20).set('class', 2); }));
if (typeof manualWater !== 'undefined') manual = manual.merge(manualWater.map(function (f) { return f.buffer(20).set('class', 3); }));
if (typeof manualBrush !== 'undefined') manual = manual.merge(manualBrush.map(function (f) { return f.buffer(20).set('class', 4); }));
var training = siteFC.merge(manual);

// ---- Sentinel-2 dry-season composite (Nov of year-1 to Mar of year)
function maskS2(img) {
  var qa = img.select('QA60');
  var m = qa.bitwiseAnd(1 << 10).eq(0).and(qa.bitwiseAnd(1 << 11).eq(0));
  return img.updateMask(m).divide(10000).copyProperties(img, ['system:time_start']);
}
function comp(year) {
  var c = ee.ImageCollection('COPERNICUS/S2_HARMONIZED')
    .filterBounds(roi)
    .filterDate((year - 1) + '-11-01', year + '-03-31')
    .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 20))
    .map(maskS2);
  var m = c.median();
  var ndvi = m.normalizedDifference(['B8', 'B4']).rename('NDVI');
  var mndwi = m.normalizedDifference(['B3', 'B11']).rename('MNDWI');
  var ndre = m.normalizedDifference(['B8', 'B5']).rename('NDRE');
  return m.select(['B2', 'B3', 'B4', 'B5', 'B6', 'B7', 'B8', 'B11', 'B12']).addBands([ndvi, mndwi, ndre]).clip(roi);
}
var s2proj = ee.Image(ee.ImageCollection('COPERNICUS/S2_HARMONIZED').filterBounds(roi).first()).select('B2').projection();
var bands = ['B2', 'B3', 'B4', 'B5', 'B6', 'B7', 'B8', 'B11', 'B12', 'NDVI', 'MNDWI', 'NDRE'];

// ---- STEP C: train on 2023 composite, check accuracy on held-out 30%
var img23 = comp(2023);
var samples = img23.select(bands).sampleRegions({collection: training, properties: ['class'], scale: 10, tileScale: 4})
  .randomColumn('r', 7);
var trainSet = samples.filter(ee.Filter.lt('r', 0.7));
var testSet = samples.filter(ee.Filter.gte('r', 0.7));
var rf = ee.Classifier.smileRandomForest(300).train(trainSet, 'class', bands);
var cm = testSet.classify(rf).errorMatrix('class', 'classification');
print('Training pixels', trainSet.size(), 'Test pixels', testSet.size());
print('Confusion matrix (test)', cm);
print('Overall accuracy', cm.accuracy(), 'Kappa', cm.kappa());
print('Class counts', training.aggregate_histogram('class'));

var pal = ['d73027', 'fdae61', '4575b4', 'fee08b'];
var map23 = img23.select(bands).classify(rf).setDefaultProjection(s2proj);
Map.addLayer(map23, {min: 1, max: 4, palette: pal}, 'RF 2023');
// Same model on other years (transfer; treat with caution, wet years like 2020 may confuse Mixed/Brush)
[2017, 2020].forEach(function (y) {
  Map.addLayer(comp(y).select(bands).classify(rf), {min: 1, max: 4, palette: pal}, 'RF ' + y, false);
});

// ---- STEP D: MODIS monsoon NDVI 2001-2024 for high-Prosopis vs low-Prosopis pixels + CHIRPS monsoon rain
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
  var mHi = nd.updateMask(hi).reduceRegion({reducer: ee.Reducer.mean(), geometry: roi, scale: 250, maxPixels: 1e9});
  var mLo = nd.updateMask(lo).reduceRegion({reducer: ee.Reducer.mean(), geometry: roi, scale: 250, maxPixels: 1e9});
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
