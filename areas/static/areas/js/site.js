// Small helpers used on every page:
//   1. A loading screen while a new address is being scored (it can take 10-30 seconds)
//   2. The "Use my location" button
//   3. Search suggestions while typing (typo-tolerant, keyboard friendly)

var LOADING_STEPS = [
  "Finding the address…",
  "Asking OpenStreetMap what's nearby…",
  "Looking for groceries and pharmacies…",
  "Checking bus stops and metro stations…",
  "Measuring real walking times…",
  "Adding up the score…",
];

// Shows the loading screen and changes its message every 2.5 seconds
function showLoadingScreen() {
  var loadingScreen = document.getElementById("loading");
  var stepText = document.getElementById("loading-step");
  var stepNumber = 0;

  loadingScreen.hidden = false;
  setInterval(function () {
    stepNumber = stepNumber + 1;
    if (stepNumber < LOADING_STEPS.length) {
      stepText.textContent = LOADING_STEPS[stepNumber];
    }
  }, 2500);
}

// Every form or link marked with data-loading shows the loading screen
var loadingElements = document.querySelectorAll("[data-loading]");
for (var index = 0; index < loadingElements.length; index = index + 1) {
  var element = loadingElements[index];
  if (element.tagName === "FORM") {
    element.addEventListener("submit", showLoadingScreen);
  } else {
    element.addEventListener("click", showLoadingScreen);
  }
}

// "Use my location": ask the browser for coordinates, then open /locate/?lat=..&lon=..
var locationButton = document.getElementById("use-location");
if (locationButton !== null) {
  locationButton.addEventListener("click", function () {
    if (!navigator.geolocation) {
      alert("Your browser can't share your location.");
      return;
    }
    locationButton.textContent = "📍 Finding you…";
    navigator.geolocation.getCurrentPosition(
      function (position) {
        showLoadingScreen();
        var url = locationButton.dataset.url
          + "?lat=" + position.coords.latitude.toFixed(5)
          + "&lon=" + position.coords.longitude.toFixed(5);
        window.location.href = url;
      },
      function () {
        locationButton.textContent = "📍 Use my location";
        alert("Location permission was denied.");
      }
    );
  });
}


// ---- Search suggestions -------------------------------------------------------------
//
// While you type, two requests are made:
//   1. ?local=1  -> areas we already scored, answered instantly from the database
//   2. full      -> also OpenStreetMap places (Photon), about 1-3 seconds, typo-tolerant
// "go" inputs (home page) open the chosen place; "fill" inputs (compare page) fill the box.

var SUGGEST_DELAY_MS = 300;

// Puts text into HTML safely (place names come from OpenStreetMap)
function escapeText(text) {
  var element = document.createElement("div");
  element.textContent = text;
  return element.innerHTML;
}

function setUpSuggestions(input) {
  var box = input.closest(".search-box");
  var list = box.querySelector(".suggestions");
  var mode = input.dataset.suggest;
  var currentItems = [];
  var activeIndex = -1;
  var typingTimer = null;
  var latestRequestNumber = 0;
  var fullResultsShown = false;

  // Draws the list. isStillSearching adds a "Searching…" line at the bottom.
  function showItems(items, isStillSearching) {
    currentItems = items;
    activeIndex = -1;
    var html = "";
    for (var itemIndex = 0; itemIndex < items.length; itemIndex = itemIndex + 1) {
      var item = items[itemIndex];
      var pin = item.area_id ? "★" : "📍";
      var score = item.score !== null && item.score !== undefined
        ? '<span class="suggestion-score">' + item.score + "</span>" : "";
      html = html + '<li class="suggestion" data-index="' + itemIndex + '">'
        + '<span class="suggestion-pin">' + pin + "</span>"
        + '<div class="suggestion-text"><div class="suggestion-label">' + escapeText(item.label) + "</div>"
        + '<div class="suggestion-detail">' + escapeText(item.detail || "") + "</div></div>"
        + score + "</li>";
    }
    if (isStillSearching) {
      html = html + '<li class="suggestion-note">Searching OpenStreetMap…</li>';
    } else if (items.length === 0) {
      html = html + '<li class="suggestion-note">No matches yet. Press Enter to search anyway.</li>';
    }
    list.innerHTML = html;
    list.hidden = false;
  }

  function hideList() {
    list.hidden = true;
    activeIndex = -1;
  }

  // Highlights one row (for arrow keys)
  function highlight(newIndex) {
    var rows = list.querySelectorAll(".suggestion");
    for (var rowIndex = 0; rowIndex < rows.length; rowIndex = rowIndex + 1) {
      rows[rowIndex].classList.toggle("active", rowIndex === newIndex);
    }
    activeIndex = newIndex;
  }

  // What happens when a suggestion is chosen
  function choose(item) {
    hideList();
    if (mode === "fill") {
      var firstPartOfDetail = (item.detail || "").split(",")[0];
      var isScoreText = firstPartOfDetail.indexOf("Scored") === 0;
      input.value = item.label + (firstPartOfDetail && !isScoreText ? ", " + firstPartOfDetail : "");
      return;
    }
    if (item.area_id) {
      window.location.href = "/area/" + item.area_id + "/";  // already scored: instant
      return;
    }
    showLoadingScreen();
    window.location.href = input.dataset.locateUrl
      + "?lat=" + item.lat + "&lon=" + item.lon
      + "&name=" + encodeURIComponent(item.label)
      + "&detail=" + encodeURIComponent(item.detail || "");
  }

  // Asks the server for suggestions. Old answers that arrive late are ignored.
  function fetchSuggestions(text, onlyLocal) {
    latestRequestNumber = latestRequestNumber + 1;
    var myRequestNumber = latestRequestNumber;
    var url = input.dataset.suggestUrl + "?q=" + encodeURIComponent(text) + (onlyLocal ? "&local=1" : "");

    fetch(url)
      .then(function (response) { return response.json(); })
      .then(function (data) {
        var textChanged = input.value.trim() !== text;
        if (textChanged) {
          return;
        }
        if (onlyLocal && fullResultsShown) {
          return;  // the fuller answer already arrived
        }
        if (!onlyLocal && myRequestNumber !== latestRequestNumber && fullResultsShown) {
          return;
        }
        if (!onlyLocal) {
          fullResultsShown = true;
        }
        showItems(data.results || [], onlyLocal);
      })
      .catch(function () {
        // Suggestions are optional: if they fail, normal search still works
      });
  }

  input.addEventListener("input", function () {
    clearTimeout(typingTimer);
    var text = input.value.trim();
    fullResultsShown = false;
    if (text.length < 2) {
      hideList();
      return;
    }
    fetchSuggestions(text, true);  // instant: already-scored areas
    typingTimer = setTimeout(function () {
      fetchSuggestions(text, false);  // fuller: OpenStreetMap places
    }, SUGGEST_DELAY_MS);
  });

  input.addEventListener("keydown", function (event) {
    if (list.hidden || currentItems.length === 0) {
      return;
    }
    if (event.key === "ArrowDown") {
      event.preventDefault();
      highlight((activeIndex + 1) % currentItems.length);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      highlight(activeIndex <= 0 ? currentItems.length - 1 : activeIndex - 1);
    } else if (event.key === "Enter" && activeIndex >= 0) {
      event.preventDefault();
      choose(currentItems[activeIndex]);
    } else if (event.key === "Escape") {
      hideList();
    }
  });

  // mousedown (not click) so it fires before the input loses focus
  list.addEventListener("mousedown", function (event) {
    var row = event.target.closest(".suggestion");
    if (row !== null) {
      event.preventDefault();
      choose(currentItems[Number(row.dataset.index)]);
    }
  });

  input.addEventListener("blur", function () {
    setTimeout(hideList, 120);
  });
}

var suggestInputs = document.querySelectorAll("[data-suggest]");
for (var inputIndex = 0; inputIndex < suggestInputs.length; inputIndex = inputIndex + 1) {
  setUpSuggestions(suggestInputs[inputIndex]);
}
