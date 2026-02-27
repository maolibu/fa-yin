// 竖排单栏调试脚本 — 在浏览器控制台运行
(function () {
    var el = document.getElementById('reader-content');
    if (!el) { console.log('reader-content not found'); return; }
    var cs = getComputedStyle(el);
    console.log('=== juan-body (#reader-content) ===');
    console.log('scrollWidth:', el.scrollWidth, 'clientWidth:', el.clientWidth);
    console.log('scrollLeft:', el.scrollLeft);
    console.log('overflow-x:', cs.overflowX, 'overflow-y:', cs.overflowY);
    console.log('height:', cs.height, 'width:', cs.width);
    console.log('writing-mode:', cs.writingMode);
    console.log('display:', cs.display, 'flex:', cs.flex);

    var parent = el.parentElement;
    var pcs = getComputedStyle(parent);
    console.log('=== parent ===');
    console.log('id:', parent.id, 'class:', parent.className);
    console.log('display:', pcs.display, 'flexDirection:', pcs.flexDirection);
    console.log('overflow:', pcs.overflow, 'width:', pcs.width, 'height:', pcs.height);

    var layout = document.getElementById('reader-layout');
    var lcs = getComputedStyle(layout);
    console.log('=== reader-layout ===');
    console.log('classes:', layout.className);
    console.log('overflow:', lcs.overflow, 'height:', lcs.height);
})();
