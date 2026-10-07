// The map on the area page (Leaflet + OpenStreetMap data).
//
// The page puts all the data in a <script id="map-data"> tag (Django's json_script),
// so no extra request is needed.

var mapData = JSON.parse(document.getElementById("map-data").textContent);

// Step 1: the map, centred on the address. The tiles are OpenStreetMap's own (free, no key);
// CSS turns them grey (see .leaflet-tile-pane in style.css) so the coloured dots stand out.
var map = L.map("map", { scrollWheelZoom: false }).setView(mapData.center, 15);
L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 19,
  referrerPolicy: "strict-origin-when-cross-origin",  // OpenStreetMap blocks tiles without a Referer
  attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
}).addTo(map);

// Step 2: the 15-minute walking circle
var walkCircle = L.circle(mapData.center, {
  radius: mapData.radius,
  color: "#111111",
  weight: 1.5,
  dashArray: "6 6",
  fillColor: "#111111",
  fillOpacity: 0.03,
}).addTo(map);
map.fitBounds(walkCircle.getBounds(), { padding: [10, 10] });

// Step 3: one layer per category, so each can be switched on and off
var categoryInfo = {};
var categoryLayers = {};
var placeCounts = {};
for (var index = 0; index < mapData.categories.length; index = index + 1) {
  var category = mapData.categories[index];
  categoryInfo[category.key] = category;
  categoryLayers[category.key] = L.layerGroup().addTo(map);
  placeCounts[category.key] = 0;
}

// Step 4: a coloured dot for every place
for (var placeIndex = 0; placeIndex < mapData.places.length; placeIndex = placeIndex + 1) {
  var place = mapData.places[placeIndex];
  var info = categoryInfo[place.category];
  var walkMinutes = Math.round(place.distance * 1.3 / 80);

  var marker = L.circleMarker([place.lat, place.lon], {
    radius: 6,
    color: "#ffffff",
    weight: 1.5,
    fillColor: info.color,
    fillOpacity: 0.95,
  });
  marker.bindPopup(
    "<strong>" + info.icon + " " + escapeHtml(place.name) + "</strong><br>"
    + info.label + " · " + place.distance + " m · ~" + walkMinutes + " min walk"
  );
  marker.addTo(categoryLayers[place.category]);
  placeCounts[place.category] = placeCounts[place.category] + 1;
}

// Step 5: the home marker (a pulsing black dot)
var homeIcon = L.divIcon({ className: "", html: '<div class="home-marker"></div>', iconSize: [18, 18] });
L.marker(mapData.center, { icon: homeIcon, zIndexOffset: 1000 })
  .bindPopup("<strong>" + escapeHtml(mapData.name) + "</strong><br>15-minute walk shown by the circle")
  .addTo(map);

// Step 6: the legend. Click a category to hide or show its dots.
var legend = document.getElementById("legend");
for (var legendIndex = 0; legendIndex < mapData.categories.length; legendIndex = legendIndex + 1) {
  var legendCategory = mapData.categories[legendIndex];
  if (placeCounts[legendCategory.key] === 0) {
    continue;
  }
  var label = document.createElement("label");
  label.innerHTML = '<input type="checkbox" checked>'
    + '<span class="dot" style="background:' + legendCategory.color + '"></span>'
    + legendCategory.label + " · " + placeCounts[legendCategory.key];
  label.dataset.category = legendCategory.key;
  label.addEventListener("click", toggleCategory);
  legend.appendChild(label);
}

// Hides or shows one category's dots
function toggleCategory(event) {
  event.preventDefault();
  var label = event.currentTarget;
  var layer = categoryLayers[label.dataset.category];
  if (map.hasLayer(layer)) {
    map.removeLayer(layer);
    label.classList.add("off");
  } else {
    map.addLayer(layer);
    label.classList.remove("off");
  }
}

// Place names come from OpenStreetMap, so never put them into HTML unescaped
function escapeHtml(text) {
  var element = document.createElement("div");
  element.textContent = text;
  return element.innerHTML;
}
