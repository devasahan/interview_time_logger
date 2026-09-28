// Live "Duration: 1h 30m" preview on the interview form.
(function () {
  var form = document.getElementById("interview-form");
  if (!form) return;
  var start = form.querySelector('[name="start_time"]');
  var end = form.querySelector('[name="end_time"]');
  var output = document.getElementById("duration-preview");
  var MAX_MINUTES = 12 * 60;

  function toMinutes(value) {
    var parts = value.split(":");
    return Number(parts[0]) * 60 + Number(parts[1]);
  }

  function format(minutes) {
    var h = Math.floor(minutes / 60);
    var m = minutes % 60;
    if (h && m) return h + "h " + (m < 10 ? "0" : "") + m + "m";
    return h ? h + "h" : m + "m";
  }

  function update() {
    output.classList.remove("warn");
    if (!start.value || !end.value) {
      output.textContent = "";
      return;
    }
    var diff = toMinutes(end.value) - toMinutes(start.value);
    if (diff === 0) {
      output.textContent = "Start and end times are the same.";
      output.classList.add("warn");
      return;
    }
    var nextDay = diff < 0;
    if (nextDay) diff += 24 * 60;
    if (diff > MAX_MINUTES) {
      output.textContent = "That's " + format(diff) + ". Check the times (maximum 12 hours).";
      output.classList.add("warn");
      return;
    }
    output.textContent = "Duration: " + format(diff) + (nextDay ? " (ends the next day)" : "");
  }

  start.addEventListener("input", update);
  end.addEventListener("input", update);
  update();
})();
