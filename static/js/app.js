// Navigation drawer, account menu, section links, copy buttons, messages and table fitting.
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
  // The account menu is a <details> element: close it on outside clicks and Escape.
  var menus = document.querySelectorAll("[data-menu]");
  function closeMenus(except) {
    menus.forEach(function (menu) {
      if (menu !== except) menu.open = false;
    });
  }
  document.addEventListener("click", function (event) {
    closeMenus(event.target.closest ? event.target.closest("[data-menu]") : null);
  });

  document.addEventListener("keydown", function (event) {
    if (event.key !== "Escape") return;
    setOpen(false);
    closeMenus(null);
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

  // Messages. On members' pages they float in the corner, and success messages leave by
  // themselves after a few seconds (not while the pointer or keyboard focus is on them).
  var reduceMotion = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  function dismiss(alert) {
    if (!alert || alert.classList.contains("leaving")) return;
    if (reduceMotion || !alert.closest(".toasts")) {
      alert.remove();
      return;
    }
    alert.classList.add("leaving");
    setTimeout(function () { alert.remove(); }, 220);
  }
  document.querySelectorAll("[data-dismiss]").forEach(function (button) {
    button.addEventListener("click", function () { dismiss(button.closest(".alert")); });
  });
  document.querySelectorAll("[data-autohide]").forEach(function (alert) {
    var timer = null;
    var held = false;
    function schedule() {
      clearTimeout(timer);
      timer = setTimeout(function () { if (!held) dismiss(alert); }, 6000);
    }
    function hold() { held = true; clearTimeout(timer); }
    function release() { held = false; schedule(); }
    alert.addEventListener("mouseenter", hold);
    alert.addEventListener("mouseleave", release);
    alert.addEventListener("focusin", hold);
    alert.addEventListener("focusout", release);
    schedule();
  });

  // Members' top bar links to the sections of their page; mark the one being read.
  var sectionLinks = document.querySelectorAll('.appnav a[href^="#"]');
  var sections = [];
  sectionLinks.forEach(function (link) {
    var section = document.getElementById(link.getAttribute("href").slice(1));
    if (section) sections.push({ link: link, section: section });
  });
  // A section named in the address (after saving an entry) or just clicked stays marked
  // until the reader scrolls on their own.
  var pinned = location.hash.slice(1);
  function markSection() {
    var line = window.innerHeight * 0.35;
    var current = sections[0];
    sections.forEach(function (item) {
      if (item.section.getBoundingClientRect().top <= line) current = item;
    });
    var root = document.documentElement;
    if (window.innerHeight + window.scrollY >= root.scrollHeight - 2) current = sections[sections.length - 1];
    sections.forEach(function (item) {
      if (item.section.id === pinned) current = item;
    });
    sections.forEach(function (item) {
      if (item === current) item.link.setAttribute("aria-current", "location");
      else item.link.removeAttribute("aria-current");
    });
  }
  if (sections.length) {
    sections.forEach(function (item) {
      item.link.addEventListener("click", function () { pinned = item.section.id; markSection(); });
    });
    ["wheel", "touchmove", "keydown"].forEach(function (name) {
      window.addEventListener(name, function () { pinned = ""; }, { passive: true });
    });
    var marking = false;
    window.addEventListener("scroll", function () {
      if (marking) return;
      marking = true;
      requestAnimationFrame(function () { marking = false; markSection(); });
    }, { passive: true });
    markSection();
  }

  // Approving a new member: the rate is per bid for virtual assistants, per hour otherwise.
  document.querySelectorAll("[data-rate-unit-for]").forEach(function (select) {
    var input = document.getElementById(select.getAttribute("data-rate-unit-for"));
    if (!input) return;
    select.addEventListener("change", function () {
      input.placeholder = !select.value ? "Rate" : select.value === "virtual_assistant" ? "Rate / bid" : "Rate / h";
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
