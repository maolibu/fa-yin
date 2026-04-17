#!/usr/bin/env python3
"""
生成墨痕圓相（Ensō）SVG 圖標
每個圖標：手繪感的圈 + 中間的書法字
輸出為 SVG 文件，可直接在網頁中使用
"""
import math
import random
import os

# 確保可重複
random.seed(42)

def gen_enso_path(cx, cy, r, variation=0.08):
    """
    生成一個帶有手繪變化的近似圓形路徑
    使用多段貝塞爾曲線模擬毛筆墨痕
    """
    points = 24  # 採樣點數
    coords = []
    for i in range(points):
        angle = 2 * math.pi * i / points
        # 半徑隨機波動，模擬墨痕不均
        dr = r * (1 + random.uniform(-variation, variation))
        x = cx + dr * math.cos(angle)
        y = cy + dr * math.sin(angle)
        coords.append((x, y))
    
    # 構建平滑路徑（三次貝塞爾）
    path = f"M {coords[0][0]:.1f} {coords[0][1]:.1f} "
    for i in range(len(coords)):
        p0 = coords[i]
        p1 = coords[(i + 1) % len(coords)]
        p2 = coords[(i + 2) % len(coords)]
        # 控制點
        cp1x = p0[0] + (p1[0] - coords[(i - 1) % len(coords)][0]) * 0.25
        cp1y = p0[1] + (p1[1] - coords[(i - 1) % len(coords)][1]) * 0.25
        cp2x = p1[0] - (p2[0] - p0[0]) * 0.25
        cp2y = p1[1] - (p2[1] - p0[1]) * 0.25
        path += f"C {cp1x:.1f} {cp1y:.1f}, {cp2x:.1f} {cp2y:.1f}, {p1[0]:.1f} {p1[1]:.1f} "
    
    path += "Z"
    return path


def gen_enso_svg(char, color, circle_color, filename):
    """
    生成單個 Ensō SVG 圖標
    char: 中間的漢字
    color: 字的顏色
    circle_color: 圈的顏色
    """
    size = 256
    cx, cy = size / 2, size / 2
    r = 100  # 圈半徑

    # 圈的筆畫寬度有變化（模擬毛筆粗細）
    # 用兩層：外圈粗、內圈略細，製造墨痕層次
    path1 = gen_enso_path(cx, cy, r, variation=0.06)
    
    # 留一個小缺口（禪宗圓相的特徵）— 通過 dasharray 實現
    # 實際用 stroke 而非 fill，更接近書法
    
    # 重新用 stroke 方式
    random.seed(42)  # 重置種子保持一致
    
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size} {size}" width="{size}" height="{size}">
  <defs>
    <filter id="ink-blur-{char}" x="-10%" y="-10%" width="120%" height="120%">
      <feGaussianBlur in="SourceGraphic" stdDeviation="0.8"/>
    </filter>
    <filter id="rough-{char}" x="-10%" y="-10%" width="120%" height="120%">
      <feTurbulence type="fractalNoise" baseFrequency="0.04" numOctaves="4" result="noise"/>
      <feDisplacementMap in="SourceGraphic" in2="noise" scale="3" xChannelSelector="R" yChannelSelector="G"/>
    </filter>
  </defs>
  
  <!-- 墨痕圓相 — 用 stroke 模擬毛筆 -->
  <circle cx="{cx}" cy="{cy}" r="{r}" 
    fill="none" 
    stroke="{circle_color}" 
    stroke-width="6"
    stroke-linecap="round"
    stroke-dasharray="580 50"
    stroke-dashoffset="30"
    opacity="0.85"
    filter="url(#rough-{char})"
    transform="rotate(-30 {cx} {cy})"
  />
  
  <!-- 第二層：略粗的墨跡，增加厚度感 -->
  <circle cx="{cx}" cy="{cy}" r="{r}" 
    fill="none" 
    stroke="{circle_color}" 
    stroke-width="3"
    stroke-linecap="round"
    stroke-dasharray="400 230"
    stroke-dashoffset="60"
    opacity="0.4"
    transform="rotate(15 {cx} {cy})"
  />

  <!-- 中間的書法字 -->
  <text x="{cx}" y="{cy}" 
    text-anchor="middle" 
    dominant-baseline="central"
    font-family="'Noto Serif TC', 'Noto Serif CJK TC', 'Source Han Serif TC', 'KaiTi', '楷體', serif"
    font-size="80"
    font-weight="900"
    fill="{color}"
    filter="url(#ink-blur-{char})"
    letter-spacing="0"
  >{char}</text>
</svg>'''
    
    filepath = os.path.join(os.path.dirname(__file__), filename)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(svg)
    print(f"已生成: {filepath}")


if __name__ == '__main__':
    # 燻 — 金色系（案頭）
    gen_enso_svg('燻', '#d4a853', '#a07a30', 'enso_xun.svg')
    
    # 燈 — 玄青色（祖師）
    gen_enso_svg('燈', '#7a9ab8', '#4a6a80', 'enso_deng.svg')
    
    # 藏 — 琥珀色（貝闕）
    gen_enso_svg('藏', '#b08a50', '#806030', 'enso_zang.svg')
    
    print("全部完成！")
