#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
字體除錯腳本
用於檢查系統中可用的字體並測試中文顯示
"""

import matplotlib
matplotlib.use('Agg')  # 使用非互動式後端
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import os

def check_system_fonts():
    """檢查系統中可用的字體"""
    print("=== 系統字體檢查 ===")
    
    # 檢查所有可用字體
    fonts = [f.name for f in fm.fontManager.ttflist]
    print(f"系統中總共有 {len(fonts)} 種字體")
    
    # 尋找中文相關字體
    chinese_fonts = [f for f in fonts if any(keyword in f.lower() for keyword in ['cjk', 'chinese', 'noto', 'han', 'simsun', 'simhei', 'wenquanyi'])]
    
    if chinese_fonts:
        print(f"找到 {len(chinese_fonts)} 種可能的中文字體:")
        for font in chinese_fonts:
            print(f"  - {font}")
    else:
        print("未找到明顯的中文字體")
    
    # 檢查字體檔案路徑
    font_paths = [
        '/usr/share/fonts/opentype/noto/',
        '/usr/share/fonts/truetype/noto/',
        '/usr/share/fonts/noto-cjk/',
        '/usr/share/fonts/truetype/dejavu/',
        '/usr/share/fonts/truetype/liberation/',
    ]
    
    print("\n=== 字體檔案路徑檢查 ===")
    for path in font_paths:
        if os.path.exists(path):
            files = os.listdir(path)
            cjk_files = [f for f in files if 'cjk' in f.lower() or 'chinese' in f.lower()]
            print(f"{path}: {len(files)} 個檔案")
            if cjk_files:
                print(f"  CJK 相關檔案: {cjk_files}")
        else:
            print(f"{path}: 不存在")

def test_chinese_display():
    """測試中文顯示"""
    print("\n=== 中文顯示測試 ===")
    
    # 嘗試不同的字體設定
    font_tests = [
        ('default', None),
        ('Noto Sans CJK TC', 'Noto Sans CJK TC'),
        ('Noto Sans CJK SC', 'Noto Sans CJK SC'),
        ('DejaVu Sans', 'DejaVu Sans'),
        ('sans-serif', 'sans-serif'),
    ]
    
    for font_name, font_family in font_tests:
        try:
            plt.figure(figsize=(8, 6))
            
            if font_family:
                plt.rcParams['font.family'] = font_family
            
            plt.rcParams['axes.unicode_minus'] = False
            
            # 測試中文文字
            plt.text(0.5, 0.5, '測試中文顯示：節點ID、平均接收率', 
                    ha='center', va='center', fontsize=14, transform=plt.gca().transAxes)
            
            plt.title(f'字體測試: {font_name}', fontsize=16)
            plt.xlabel('X軸標籤（中文）', fontsize=12)
            plt.ylabel('Y軸標籤（中文）', fontsize=12)
            
            # 儲存測試圖片
            output_file = f'font_test_{font_name.replace(" ", "_")}.png'
            plt.savefig(output_file, dpi=150, bbox_inches='tight')
            plt.close()
            
            print(f"  {font_name}: 成功生成 {output_file}")
            
        except Exception as e:
            print(f"  {font_name}: 失敗 - {e}")

def install_font_suggestions():
    """提供字體安裝建議"""
    print("\n=== 字體安裝建議 ===")
    
    suggestions = [
        "sudo apt-get update",
        "sudo apt-get install -y fonts-noto-cjk fonts-noto-cjk-extra",
        "sudo apt-get install -y fonts-wqy-zenhei fonts-wqy-microhei",
        "sudo fc-cache -f -v",
        "sudo fc-list | grep -i cjk",
    ]
    
    print("建議執行以下命令安裝和配置中文字體:")
    for cmd in suggestions:
        print(f"  {cmd}")

if __name__ == "__main__":
    check_system_fonts()
    test_chinese_display()
    install_font_suggestions()
    
    print("\n=== 執行完成 ===")
    print("請檢查生成的 font_test_*.png 檔案來確認哪種字體設定有效")