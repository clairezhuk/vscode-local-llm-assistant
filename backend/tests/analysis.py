import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np
import glob
import os
import re

# Налаштування стилю
plt.style.use('dark_background')
RESULTS_DIR = "results"
SAVE_BASE_PATH = "results/analysis"
MODES_ORDER = ["fast", "thinking"]

def get_next_analysis_path():
    if not os.path.exists(SAVE_BASE_PATH):
        os.makedirs(SAVE_BASE_PATH, exist_ok=True)
    
    existing_dirs = [d for d in os.listdir(SAVE_BASE_PATH) if os.path.isdir(os.path.join(SAVE_BASE_PATH, d))]
    indices = [int(re.findall(r'\d+', d)[0]) for d in existing_dirs if re.findall(r'\d+', d)]
    
    next_idx = max(indices) + 1 if indices else 0
    path = os.path.join(SAVE_BASE_PATH, f"v{next_idx}")
    os.makedirs(path, exist_ok=True)
    return path

def load_and_prepare_data():
    csv_files = glob.glob(os.path.join(RESULTS_DIR, "*.csv"))
    if not csv_files:
        print("❌ No CSV files found in results/")
        return None
    
    all_data = []
    for file in csv_files:
        df = pd.read_csv(file)
        # Визначаємо назву блоку з імені файлу
        suite_name = os.path.basename(file).replace('.csv', '').replace('_', ' ').upper()
        df['suite'] = suite_name
        # Витягуємо числовий індекс з ID (наприклад L1-BA-001 -> 1)
        df['test_idx'] = df['id'].apply(lambda x: int(re.findall(r'\d+', x)[-1]))
        all_data.append(df)
    
    full_df = pd.concat(all_data, ignore_index=True)
    # Конвертуємо success в булевий тип про всяк випадок
    full_df['success'] = full_df['success'].astype(bool)
    return full_df

# --- 0. Text Stats ---
def export_text_stats(df, path):
    with open(os.path.join(path, "0_text_stats.txt"), "w", encoding="utf-8") as f:
        f.write("=== BENCHMARK AGGREGATED STATISTICS ===\n\n")
        
        # Агрегуємо по тестах (один тест = сукупність спроб)
        test_summary = df.groupby(['suite', 'id', 'processing_type']).agg({
            'success': ['sum', 'count', 'all', 'any']
        }).reset_index()
        test_summary.columns = ['suite', 'id', 'mode', 'success_sum', 'total_attempts', 'full_pass', 'partial_pass']

        for mode in MODES_ORDER:
            m_df = test_summary[test_summary['mode'] == mode]
            if m_df.empty: continue
            
            total_tests = len(m_df)
            full_passes = m_df['full_pass'].sum()
            partial_passes = m_df['partial_pass'].sum()
            
            # Статистика на рівні спроб (attempts)
            raw_mode_df = df[df['processing_type'] == mode]
            total_attempts = len(raw_mode_df)
            total_successes = raw_mode_df['success'].sum()
            success_rate = (total_successes / total_attempts) * 100
            
            f.write(f"MODE: {mode.upper()}\n")
            f.write(f"  - Total Tests: {total_tests}\n")
            f.write(f"  - Full Pass (All repeats ok): {full_passes} ({full_passes/total_tests*100:.1f}%)\n")
            f.write(f"  - Partial Pass (At least one ok): {partial_passes} ({partial_passes/total_tests*100:.1f}%)\n")
            f.write(f"  - Attempt-level Success Rate: {success_rate:.1f}% ({total_successes}/{total_attempts})\n")
            f.write("-" * 45 + "\n")

# --- 1. Percentage Heatmap ---
def plot_1_heatmaps(df, path):
    suites = sorted(df['suite'].unique())
    max_tests = df['test_idx'].max()
    
    # Агрегуємо успішність спроб у відсотки (0.0 - 1.0) для кожного тесту
    pivot_df = df.groupby(['test_idx', 'suite', 'processing_type'])['success'].mean().reset_index()

    fig, axes = plt.subplots(1, 2, figsize=(14, 10), sharey=True)
    
    for i, mode in enumerate(MODES_ORDER):
        mode_data = pivot_df[pivot_df['processing_type'] == mode]
        matrix = mode_data.pivot(index='test_idx', columns='suite', values='success')
        
        # Дозаповнюємо індекси, щоб сітка була повною
        matrix = matrix.reindex(range(1, max_tests + 1))
        
        sns.heatmap(matrix, ax=axes[i], cmap="RdYlGn", vmin=0, vmax=1, 
                    mask=matrix.isnull(), linewidths=0.5, linecolor='#222', cbar_kws={'label': 'Success Ratio'})
        
        axes[i].set_facecolor('#111') # Чорний для порожніх клітинок
        axes[i].set_title(f"Success %: {mode.upper()}", fontsize=14, pad=15)
        axes[i].set_xlabel("Test Suite")
        axes[i].set_ylabel("Test Index")
        axes[i].set_xticklabels(axes[i].get_xticklabels(), rotation=45, ha='right')

    plt.tight_layout()
    plt.savefig(os.path.join(path, "1_percentage_heatmap.png"), dpi=150)

# --- 2. Bars by Suite and Intent ---
def plot_2_bars(df, path):
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 10))
    
    # By Suite
    suite_agg = df.groupby(['suite', 'processing_type'])['success'].mean().reset_index()
    sns.barplot(data=suite_agg, x='suite', y='success', hue='processing_type', 
                palette='viridis', ax=ax1)
    ax1.set_title("Success Ratio by Suite")
    ax1.set_ylim(0, 1.1)
    ax1.set_ylabel("Success Rate")
    ax1.tick_params(axis='x', rotation=15)

    # By Intent
    intent_map = {1: '1: Theory', 2: '2: Coding', 3: '3: CLI'}
    df['intent_label'] = df['intent'].map(intent_map)
    intent_agg = df.groupby(['intent_label', 'processing_type'])['success'].mean().reset_index()
    sns.barplot(data=intent_agg, x='intent_label', y='success', hue='processing_type', 
                palette='viridis', ax=ax2)
    ax2.set_title("Success Ratio by Intent Type")
    ax2.set_ylim(0, 1.1)
    ax2.set_ylabel("Success Rate")

    plt.tight_layout()
    plt.savefig(os.path.join(path, "2_bars_comparison.png"))

# --- 3. Latency Histograms ---
def plot_3_latency_hist(df, path):
    fig, axes = plt.subplots(1, 2, figsize=(14, 6), sharex=True)
    
    # Визначаємо спільний масштаб для X
    x_max = df['time_s'].max() * 1.05
    
    for i, mode in enumerate(MODES_ORDER):
        mode_data = df[df['processing_type'] == mode]
        sns.histplot(mode_data['time_s'], ax=axes[i], bins=30, kde=True, color='cyan' if mode=='fast' else 'magenta')
        axes[i].set_title(f"Latency Distribution: {mode.upper()}")
        axes[i].set_xlabel("Time (seconds)")
        axes[i].set_xlim(0, x_max)
        
        # Додаємо медіану на графік
        median = mode_data['time_s'].median()
        axes[i].axvline(median, color='white', linestyle='--', label=f'Median: {median:.1f}s')
        axes[i].legend()

    plt.tight_layout()
    plt.savefig(os.path.join(path, "3_latency_histograms.png"))

# --- 4. Latency Boxplots by Suite ---
def plot_4_latency_box(df, path):
    plt.figure(figsize=(14, 8))
    sns.boxplot(data=df, x='suite', y='time_s', hue='processing_type', palette='Set2')
    plt.title("Latency Distribution per Test Block", fontsize=15)
    plt.xticks(rotation=25)
    plt.ylabel("Time (seconds)")
    plt.grid(axis='y', alpha=0.2)
    
    plt.tight_layout()
    plt.savefig(os.path.join(path, "4_latency_boxplots.png"))

def main():
    print("🚀 Loading data...")
    df = load_and_prepare_data()
    if df is None: return

    analysis_dir = get_next_analysis_path()
    print(f"📂 Analysis version: {os.path.basename(analysis_dir)}")

    print("📝 Exporting text stats...")
    export_text_stats(df, analysis_dir)

    print("📊 Generating heatmaps...")
    plot_1_heatmaps(df, analysis_dir)

    print("📉 Generating bar charts...")
    plot_2_bars(df, analysis_dir)

    print("⏱️ Analyzing latency...")
    plot_3_latency_hist(df, analysis_dir)
    plot_4_latency_box(df, analysis_dir)

    print(f"✅ Analysis complete! Results saved in: {analysis_dir}")

if __name__ == "__main__":
    main()