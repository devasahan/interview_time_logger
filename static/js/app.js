// Mobile navigation drawer, copy buttons, dismissible messages and table fitting.
(function () {
  var app = document.querySelector(".app");
  var toggle = document.querySelector("[data-nav-toggle]");

  function setOpen(open) {
    if (!app || !toggle) return;
    app.classList.toggle("nav-open", open);
    toggle.setAttribute("aria-expanded", open ? "true" : "false");
  }

  if (toggle) {
    toggle.addEventListener("click", function () {
      setOpen(!app.classList.contains("nav-open"));
    });
  }
  document.querySelectorAll("[data-nav-close]").forEach(function (el) {
    el.addEventListener("click", function () { setOpen(false); });
  });
  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape") setOpen(false);
  });

  document.querySelectorAll("[data-copy]").forEach(function (button) {
    button.addEventListener("click", function () {
      var input = document.getElementById(button.getAttribute("data-copy"));
      if (!input) return;
      input.select();
      var done = function () {
        var label = button.querySelector("[data-copy-label]");
        if (!label) return;
        var original = label.textContent;
        label.textContent = "Copied";
        setTimeout(function () { label.textContent = original; }, 1600);
      };
      if (navigator.clipboard) {
        navigator.clipboard.writeText(input.value).then(done, function () { document.execCommand("copy"); done(); });
      } else {
        document.execCommand("copy");
        done();
      }
    });
  });

  document.querySelectorAll("[data-dismiss]").forEach(function (button) {
    button.addEventListener("click", function () {
      var alert = button.closest(".alert");
      if (alert) alert.remove();
    });
  });

  // Tables in cards narrower than 940px are stacked by app.css. Show the normal table
  // wherever all its columns fit (on phones the stacked cards read better, so keep them).
  // Tables with the same columns switch together, so a month's weeks all look alike.
  var tables = document.querySelectorAll(".table.responsive");
  function columnsOf(table) {
    return table.tHead ? table.tHead.textContent : "";
  }
  function fitTables() {
    var tooWide = {};
    tables.forEach(function (table) {
      var wrap = table.parentElement;
      table.classList.add("fits");
      if (wrap.clientWidth < 600 || wrap.scrollWidth > wrap.clientWidth) tooWide[columnsOf(table)] = true;
    });
    tables.forEach(function (table) {
      table.classList.toggle("fits", !tooWide[columnsOf(table)]);
    });
  }
  if (tables.length) {
    var pending = false;
    fitTables();
    window.addEventListener("resize", function () {
      if (pending) return;
      pending = true;
      requestAnimationFrame(function () { pending = false; fitTables(); });
    });
    if (document.fonts) document.fonts.ready.then(fitTables);
  }
})();
