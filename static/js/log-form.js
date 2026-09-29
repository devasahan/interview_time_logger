// Log forms: live "Duration: 1h 30m" under the times, and the pay card beside the form
// ("56 bids × $0.08" → $4.48). Amounts are rounded like the server: to the cent, halves up.
(function () {
  var form = document.querySelector("[data-log-form]");
  if (!form) return;
  var timed = form.getAttribute("data-log-form") === "time";
  var date = form.querySelector('[name="date"]');
  var start = form.querySelector('[name="start_time"]');
  var end = form.querySelector('[name="end_time"]');
  var bids = form.querySelector('[name="bids"]');
  var durationOut = document.getElementById("duration-preview");
  var card = document.querySelector("[data-pay-preview]");
  var ratesData = document.getElementById("pay-rates");
  var rates = ratesData ? JSON.parse(ratesData.textContent) : [];
  var MAX_MINUTES = 12 * 60;

  function toMinutes(value) {
    var parts = value.split(":");
    return Number(parts[0]) * 60 + Number(parts[1]);
  }

  function formatDuration(minutes) {
    var h = Math.floor(minutes / 60);
    var m = minutes % 60;
    if (h && m) return h + "h " + (m < 10 ? "0" : "") + m + "m";
    return h ? h + "h" : m + "m";
  }

  // Minutes between the start and end time; an end at or before the start is the next day.
  function worked() {
    if (!start.value || !end.value) return { empty: true };
    var diff = toMinutes(end.value) - toMinutes(start.value);
    if (diff === 0) return { problem: "Start and end times are the same." };
    var nextDay = diff < 0;
    if (nextDay) diff += 24 * 60;
    if (diff > MAX_MINUTES) return { problem: "That's " + formatDuration(diff) + ". Check the times (maximum 12 hours).", minutes: diff };
    return { minutes: diff, nextDay: nextDay };
  }

  function showDuration(time) {
    if (!durationOut) return;
    durationOut.classList.toggle("warn", Boolean(time.problem));
    if (time.problem) durationOut.textContent = time.problem;
    else if (time.empty) durationOut.textContent = "";
    else durationOut.textContent = "Duration: " + formatDuration(time.minutes) + (time.nextDay ? " (ends the next day)" : "");
  }

  if (!card) {
    if (timed) {
      var onTime = function () { showDuration(worked()); };
      start.addEventListener("input", onTime);
      end.addEventListener("input", onTime);
      onTime();
    }
    return;
  }

  var amountOut = card.querySelector("[data-pay-amount]");
  var formulaOut = card.querySelector("[data-pay-formula]");
  var rateOut = card.querySelector("[data-pay-rate]");
  var symbol = card.getAttribute("data-currency");
  var unitWord = card.getAttribute("data-unit-word");

  function showAmount(cents) {
    amountOut.classList.toggle("is-empty", cents === null);
    amountOut.textContent = money(cents === null ? 0 : cents);
  }

  function money(cents) {
    var whole = String(Math.floor(cents / 100)).replace(/\B(?=(\d{3})+(?!\d))/g, ",");
    var rest = cents % 100;
    return symbol + whole + "." + (rest < 10 ? "0" : "") + rest;
  }

  // The rate in cents on a day: the latest one that started by then. A member's first
  // rate also covers earlier days (the server does the same).
  function rateOn(day) {
    if (!rates.length) return null;
    var chosen = rates[0][1];
    rates.forEach(function (item) {
      if (item[0] <= day) chosen = item[1];
    });
    return Math.round(Number(chosen) * 100);
  }

  function update() {
    var time = timed ? worked() : null;
    if (timed) showDuration(time);

    var rate = rateOn(date.value || card.getAttribute("data-today"));
    if (rate === null) {
      showAmount(null);
      formulaOut.textContent = "No rate is set yet.";
      return;
    }
    rateOut.textContent = money(rate) + " per " + unitWord;

    if (timed) {
      if (time.empty || time.problem) {
        showAmount(null);
        formulaOut.textContent = time.problem ? "Check the times to see the pay." : "Enter the start and end time to see the pay.";
        return;
      }
      showAmount(Math.floor((time.minutes * rate + 30) / 60));
      formulaOut.textContent = formatDuration(time.minutes) + " × " + money(rate) + "/h";
      return;
    }

    var count = Number(bids.value);
    if (!bids.value || !(count >= 1) || Math.floor(count) !== count) {
      showAmount(null);
      formulaOut.textContent = "Enter the number of bids to see the pay.";
      return;
    }
    showAmount(count * rate);
    formulaOut.textContent = count.toLocaleString("en-US") + " bid" + (count === 1 ? "" : "s") + " × " + money(rate);
  }

  [date, start, end, bids].forEach(function (input) {
    if (!input) return;
    input.addEventListener("input", update);
    input.addEventListener("change", update);
  });
  update();
})();
