/* init-my.js —— 我页初始化：渲染九宫格 + 创建 my 引擎（点封面才 open）*/
(function () {
  var ds = createMyDataSource();
  var profilePage = document.getElementById("profilePage");
  var grid = document.getElementById("meGrid");

  function fmtNum(n) {
    n = Number(n) || 0;
    if (n >= 10000) return (n / 10000).toFixed(1).replace(/\.0$/, "") + "万";
    return String(n);
  }

  // 渲染九宫格：真封面 + 点赞角标（点赞在 stats.digg 下）
  function renderGrid(list) {
    grid.innerHTML = "";
    list.forEach(function (v, i) {
      var item = document.createElement("div");
      item.className = "me-grid-item";
      item.style.cssText = "position:relative;aspect-ratio:9/12;overflow:hidden;cursor:pointer;background:#f0f0f0;";
      var img = document.createElement("img");
      img.src = v.cover_url;
      img.loading = "lazy";
      img.style.cssText = "width:100%;height:100%;object-fit:cover;display:block;pointer-events:none;";
      item.appendChild(img);
      var likes = (Number(v.like_count) || 0);
      if (likes > 0) {
        var lb = document.createElement("div");
        lb.style.cssText = "position:absolute;bottom:4px;left:4px;color:#fff;font-size:11px;text-shadow:0 1px 2px rgba(0,0,0,.8);pointer-events:none;";
        lb.textContent = "♥ " + fmtNum(likes);
        item.appendChild(lb);
      }
      item.addEventListener("click", function () { window.__engine.open(i); });
      grid.appendChild(item);
    });
  }

  ds.all().then(function (list) {
    renderGrid(list);
    // 我页加载即显示个人主页
    profilePage.classList.add("show");
  }).catch(function (e) { console.error("render grid error", e); });

  var engine = window.createPlayerEngine({
    variant: "my",
    rootEl: document.getElementById("myPlayer"),
    sliderEl: document.getElementById("mySlider"),
    loadingEl: document.getElementById("loading"),
    toastEl: document.getElementById("toast"),
    musicPageEl: document.getElementById("musicPage"),
    dataSource: ds,
    autoStart: false
  });
  window.__engine = engine;
})();
