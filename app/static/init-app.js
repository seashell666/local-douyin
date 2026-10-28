/* init-app.js —— 单页初始化：一个共享引擎（首页为主），点"我"页封面切到 my 数据
 * 首页和我页播放共用同一个引擎和 slider，只是数据源不同；全程页面内切换不刷新、URL 不变。 */
(function () {
  var homeDs = createHomeDataSource();
  var myDs = createMyDataSource();
  var grid = document.getElementById("meGrid");

  function fmtNum(n) {
    n = Number(n) || 0;
    if (n >= 10000) return (n / 10000).toFixed(1).replace(/\.0$/, "") + "万";
    return String(n);
  }

  // 渲染九宫格：真封面 + 点赞角标
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
      var likes = Number(v.like_count) || 0;
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

  myDs.all().then(function (list) {
    renderGrid(list);
    // 我页头像：用第一条作品的作者头像
    if (list[0] && list[0].avatar_url) {
      var meAv = document.getElementById("meAvatar");
      if (meAv) meAv.src = list[0].avatar_url;
    }
    // 预热引擎 my 数据：让首次点封面时走同步路径（play() 在真实点击手势内），
    // 否则首帧会因非静音 autoplay 脱离手势被拦而停在封面
    if (engine && engine.preloadMy) engine.preloadMy();
  }).catch(function (e) { console.error("render grid error", e); });

  // 一个引擎：首页自动启动，my 数据源通过 myDataSource 传入，点封面时切换
  var engine = window.createPlayerEngine({
    variant: "home",
    rootEl: document.getElementById("stage"),
    sliderEl: document.getElementById("slider"),
    loadingEl: document.getElementById("loading"),
    toastEl: document.getElementById("toast"),
    musicPageEl: document.getElementById("musicPage"),
    dataSource: homeDs,
    myDataSource: myDs,
    autoStart: true,
    showSplash: true
  });
  window.__engine = engine;
})();
