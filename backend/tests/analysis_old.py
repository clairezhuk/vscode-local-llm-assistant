import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import seaborn as sns
import numpy as np
import glob
import os
import re
from matplotlib.ticker import MultipleLocator

# Style
plt.style.use('default')
sns.set_theme(style="whitegrid")
SAVE_BASE_PATH = "results/analysis"
CATEGORY_ORDER = ["Fast", "Planning", "Chain_of_draft", "Reflection_refine"]

def get_next_analysis_path():
    if not os.path.exists(SAVE_BASE_PATH):
        os.makedirs(SAVE_BASE_PATH)
    
    existing_dirs = [d for d in os.listdir(SAVE_BASE_PATH) if os.path.isdir(os.path.join(SAVE_BASE_PATH, d))]
    indices = [int(re.findall(r'\d+', d)[0]) for d in existing_dirs if re.findall(r'\d+', d)]
    
    next_idx = max(indices) + 1 if indices else 0
    path = os.path.join(SAVE_BASE_PATH, f"v{next_idx}")
    os.makedirs(path)
    return path

# --- Agregation ---

def parse_results(path, process_fast=True, process_think=True):
    csv_files = glob.glob(path)
    if not csv_files: return None, None, None
    all_data = []
    for file in csv_files:
        df = pd.read_csv(file)
        df['exec_ok'] = pd.to_numeric(df['exec_ok'], errors='coerce')
        df['test_idx'] = df['id'].apply(lambda x: int(re.findall(r'\d+', x)[-1]))
        df['suite'] = os.path.basename(file).replace('.csv', '').replace('_', ' ').title()
        df['success_count'] = df.apply(
            lambda r: r['format_ok'] if pd.isna(r['exec_ok']) else min(r['format_ok'], r['exec_ok']), axis=1
        )
        all_data.append(df)
    full_df = pd.concat(all_data)
    return full_df

def apply_old_data():
    fast_path = "results/original_1_5B_q4/*.csv"
    thinking_paths = [
        "results/original_1_5B_q4/1_planning_logic/*.csv",
        "results/original_1_5B_q4/2_chain_of_draft/*.csv",
        "results/original_1_5B_q4/3_reflection_refine/*.csv"
    ]
    thinking_names = ["Planning", "Chain_of_draft", "Reflection_refine"]
    
    df_fast = parse_results(fast_path)
    df_fast = df_fast[df_fast['processing_type'] == 'fast']
    df_fast['processing_type'] = "Fast"
    
    dfs = [df_fast]
    for path, name in zip(thinking_paths, thinking_names):
        df_t = parse_results(path)
        df_t = df_t[df_t['processing_type'] == 'thinking']
        df_t['processing_type'] = name
        dfs.append(df_t)
    
    full_df = pd.concat(dfs, ignore_index=True)
    categories = ["Fast"] + thinking_names
    return full_df, categories

# --- Analysis ---

def export_text_stats(df, categories, path):
    intent_map = {1: 'Theory', 2: 'Coding', 3: 'CLI'}
    df['intent_name'] = df['intent'].map(intent_map)
    
    # Helper for warning metrics
    def get_metrics(tp, fp, fn, tn):
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0
        f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0
        return precision, recall, f1

    with open(os.path.join(path, "0_text_stats.txt"), "w", encoding="utf-8") as f:
        f.write("===========================================================\n")
        f.write("===       DETAILED PERFORMANCE & WARNING REPORT         ===\n")
        f.write("===========================================================\n\n")

        # --- SECTION 1: PASS RATES (Success/Full/Partial) ---
        f.write("--- 1. PASS RATE ANALYSIS ---\n")
        levels = [('GLOBAL', []), ('BY INTENT', ['intent_name']), ('BY BLOCK', ['suite'])]
        
        for level_name, group_cols in levels:
            f.write(f"\n>> {level_name}:\n")
            cols = group_cols + ['processing_type']
            agg = df.groupby(cols).agg({
                'id': 'count',
                'success_count': 'sum',
                'repeats': 'sum'
            }).reset_index()
            
            # Additional logic for Full/Partial per scenario
            scenario_agg = df.groupby(cols + ['id']).apply(lambda x: pd.Series({
                'is_full': x['success_count'].iloc[0] == x['repeats'].iloc[0],
                'is_partial': x['success_count'].iloc[0] > 0
            })).reset_index().groupby(cols).agg({'is_full': 'sum', 'is_partial': 'sum'})
            
            agg = agg.merge(scenario_agg, on=cols)
            
            for _, row in agg.iterrows():
                prefix = f"[{row['intent_name'] if 'intent_name' in row else 'ALL'}] " if 'intent_name' in row else ""
                prefix += f"[{row['suite'] if 'suite' in row else ''}] " if 'suite' in row else ""
                f.write(f"{prefix}{row['processing_type']:18}: ")
                f.write(f"SR: {row['success_count']/row['repeats']*100:5.1f}% | ")
                f.write(f"Full: {int(row['is_full']):2}/{row['id']:2} | ")
                f.write(f"Partial: {int(row['is_partial']):2}/{row['id']:2}\n")

        # --- SECTION 2: LATENCY (All modes in one section) ---
        f.write("\n\n--- 2. LATENCY ANALYSIS (TIME S) ---\n")
        f.write(f"{'Mode':18} | {'Block':15} | {'Med':>6} | {'Mean':>6} | {'Std':>5} | {'95% CI':>14}\n")
        f.write("-" * 80 + "\n")
        
        for cat in CATEGORY_ORDER:
            if cat not in categories: continue
            c_df = df[df['processing_type'] == cat]
            
            # Overall for mode
            def write_latency_row(label, data, mode_name):
                std = data.std()
                mean = data.mean()
                ci = 1.96 * (std / np.sqrt(len(data))) if len(data) > 1 else 0
                f.write(f"{mode_name:18} | {label:15} | {data.median():6.1f} | {mean:6.1f} | {std:5.1f} | [{mean-ci:4.1f}-{mean+ci:4.1f}]\n")

            write_latency_row("OVERALL", c_df['time_s'], cat)
            for suite in sorted(c_df['suite'].unique()):
                write_latency_row(suite, c_df[c_df['suite'] == suite]['time_s'], "")
            f.write("-" * 80 + "\n")

        # --- SECTION 3: WARNING ANALYSIS ---
        f.write("\n\n--- 3. WARNINGS & MODEL HONESTY ---\n")
        for level_name, group_cols in [('GLOBAL', []), ('BY BLOCK', ['suite'])]:
            f.write(f"\n>> {level_name}:\n")
            cols = group_cols + ['processing_type']
            
            for group_keys, g_df in df.groupby(cols if cols else ['processing_type']):
                if group_keys == "Fast": continue
                
                total_att = g_df['repeats'].sum()
                rights = g_df['success_count'].sum()
                wrongs = total_att - rights
                
                fp = g_df['wrong_warnings'].sum()
                tp = g_df['warning'].sum() - fp
                fn = wrongs - tp
                tn = rights - fp
                
                prec, rec, f1 = get_metrics(tp, fp, fn, tn)
                
                # Accuracy in detection
                prevented_pct = (tp / wrongs * 100) if wrongs > 0 else 0
                false_flag_pct = (fp / rights * 100) if rights > 0 else 0
                
                label = f"{group_keys}"
                f.write(f"{label:35}: Prev: {prevented_pct:5.1f}% ({int(tp)}/{int(wrongs)}) | ")
                f.write(f"FalseFlag: {false_flag_pct:5.1f}% ({int(fp)}/{int(rights)}) | ")
                f.write(f"F1: {f1:.3f}\n")

def plot_1_general_heatmap(df, categories, path):
    suites = sorted(df['suite'].unique())
    max_tests = df['test_idx'].max()
    fig, axes = plt.subplots(1, len(categories), figsize=(4*len(categories), 10), sharey=True)
    if len(categories) == 1: axes = [axes]

    # New Colors Mapping:
    # 1: Pale Green (Right, No Warn), 2: Pale Red (Fail, No Warn)
    # 3: Bright Yellow (Correct Warns Only), 4: Bright Purple (Wrong Warns Only)
    # 5: Bright Magenta (Mixed/Disputed), 0: Empty
    colors = ['#f0f0f0', '#a5d6a7', '#ef9a9a', '#c0f000', '#d21a36', '#d009d4']
    cmap = plt.matplotlib.colors.ListedColormap(colors)

    for i, cat in enumerate(categories):
        matrix = np.zeros((max_tests, len(suites)))
        c_df = df[df['processing_type'] == cat]
        for _, row in c_df.iterrows():
            total_w = row['warning']
            wrong_w = row['wrong_warnings']
            correct_w = total_w - wrong_w
            
            if total_w == 0:
                val = 1 if row['success_count'] == row['repeats'] else 2
            else:
                if wrong_w == 0: val = 3 # Only Correct
                elif correct_w == 0: val = 4 # Only Wrong
                else: val = 5 # Disputed / Mixed
                
            matrix[row['test_idx']-1, suites.index(row['suite'])] = val
        
        ax = axes[i]
        ax.imshow(matrix, cmap=cmap, aspect='auto', vmin=0, vmax=5)
        ax.set_title(cat.upper(), fontweight='bold', pad=15)
        ax.set_xticks(np.arange(len(suites)))
        ax.set_xticklabels([s.split(' ')[0] for s in suites], rotation=45, fontsize=8)
        ax.set_yticks(np.arange(max_tests))
        ax.set_yticklabels(np.arange(1, max_tests + 1), fontsize=7)
        ax.grid(which='both', color='white', linestyle='-', linewidth=0.5)

    patches = [
        mpatches.Patch(color='#a5d6a7', label='Right (No Warn)'),
        mpatches.Patch(color='#ef9a9a', label='Fail (No Warn)'),
        mpatches.Patch(color="#c0f000", label='Correct Warnings'),
        mpatches.Patch(color="#d21a36", label='Wrong Warnings'),
        mpatches.Patch(color="#d009d4", label='Disputed (Mixed)')
    ]
    fig.legend(handles=patches, loc='lower center', bbox_to_anchor=(0.5, 0.02), ncol=3)
    plt.tight_layout(rect=[0, 0.08, 1, 1])
    plt.savefig(os.path.join(path, "1_general_heatmap.png"), dpi=150)

def plot_2_percentage_heatmap(df, categories, path):
    suites = sorted(df['suite'].unique())
    max_tests = df['test_idx'].max()
    fig, axes = plt.subplots(1, len(categories), figsize=(4*len(categories), 10), sharey=True)
    if len(categories) == 1: axes = [axes]

    for i, cat in enumerate(categories):
        matrix = np.full((max_tests, len(suites)), np.nan)
        c_df = df[df['processing_type'] == cat]
        for _, row in c_df.iterrows():
            matrix[row['test_idx']-1, suites.index(row['suite'])] = row['success_count'] / row['repeats']
        
        sns.heatmap(matrix, ax=axes[i], cmap="RdYlGn", cbar=(i == len(categories)-1), 
                    vmin=0, vmax=1, mask=np.isnan(matrix), linewidths=0.5, linecolor='#222')
        axes[i].set_facecolor('#f0f0f0')
        axes[i].set_title(f"{cat} Success %")
        axes[i].set_xticklabels([s.split(' ')[0] for s in suites], rotation=45)
        axes[i].set_yticks(np.arange(max_tests) + 0.5)
        axes[i].set_yticklabels(np.arange(1, max_tests + 1), rotation=0)

    plt.tight_layout()
    plt.savefig(os.path.join(path, "2_percentage_heatmap.png"), dpi=150)

def plot_3_4_bar_charts(df, categories, path, group_by='suite', filename="3_bars_by_suite.png"):
    plt.figure(figsize=(12, 6))
    agg = df.groupby([group_by, 'processing_type']).apply(
        lambda x: x['success_count'].sum() / x['repeats'].sum()
    ).reset_index(name='ratio')
    
    ax = sns.barplot(data=agg, x=group_by, y='ratio', hue='processing_type', 
                hue_order=[c for c in CATEGORY_ORDER if c in categories], palette='viridis')
    
    for container in ax.containers:
        ax.bar_label(container, fmt='%.2f', padding=3, fontsize=9, weight='bold')

    plt.title(f"Success Ratio by {group_by}")
    plt.xticks(rotation=30)
    plt.ylim(0, 1.15)
    plt.tight_layout()
    plt.savefig(os.path.join(path, filename))

def plot_5_6_7_latency_boxes(df, path):
    plots = [
        ('processing_type', None, "5_latency_by_mode.png"),
        ('suite', 'processing_type', "6_latency_by_suite.png"),
        ('intent_name', 'processing_type', "7_latency_by_intent.png")
    ]
    
    for x_col, hue_col, fname in plots:
        plt.figure(figsize=(13, 7))
        ax = sns.boxplot(data=df, x=x_col, y='time_s', hue=hue_col, palette='magma')
        
        # Grid and Axis config
        ax.yaxis.set_major_locator(MultipleLocator(100))
        ax.yaxis.set_minor_locator(MultipleLocator(50))
        ax.grid(which='major', axis='y', color='#CCCCCC', linestyle='-', alpha=0.7)
        ax.grid(which='minor', axis='y', color='#EEEEEE', linestyle=':', alpha=0.5)
        
        # Median labels
        # Helper to find median positions in boxplot
        lines = ax.get_lines()
        # Median lines are every 6th line in a standard boxplot
        for i in range(4, len(lines), 6):
            x_coords = lines[i].get_xdata()
            y_coords = lines[i].get_ydata()
            if len(y_coords) > 0:
                ax.text(np.mean(x_coords), y_coords[0] + 5, f'{y_coords[0]:.0f}', 
                        ha='center', va='bottom', fontsize=8, weight='bold', color='white',
                        bbox=dict(facecolor='black', alpha=0.5, edgecolor='none', pad=1))

        plt.title(f"Latency Analysis: {fname.replace('.png','')}")
        plt.xticks(rotation=20 if x_col == 'suite' else 0)
        plt.tight_layout()
        plt.savefig(os.path.join(path, fname))

# --- Warnings (8-11) ---

def plot_8_9_warning_confusion_matrices(df, categories, path, coding_only=False):
    """
    Visualizes Warning Confusion Matrices:
    TP: Wrong + Warning | TN: Right + No Warning
    FP: Right + Warning | FN: Wrong + No Warning
    """
    plot_df = df[df['intent'] == 2].copy() if coding_only else df.copy()
    suffix = "coding" if coding_only else "all"
    
    fig, axes = plt.subplots(1, len(categories), figsize=(4*len(categories), 4))
    if len(categories) == 1: axes = [axes]
    
    for i, cat in enumerate(categories):
        c_df = plot_df[plot_df['processing_type'] == cat]
        if c_df.empty: continue
        
        # Calculate attempt-level stats
        # Total attempts = repeats. We assume success_count are the 'Rights'
        rights = c_df['success_count'].sum()
        wrongs = (c_df['repeats'] - c_df['success_count']).sum()
        
        fp = c_df['wrong_warnings'].sum() # Warning on Right
        tn = rights - fp                  # No Warning on Right
        tp = c_df['warning'].sum() - fp   # Warning on Wrong
        fn = wrongs - tp                  # No Warning on Wrong
        
        matrix = np.array([[tp, fp], [fn, tn]])
        labels = [f"Warning\n({tp+fp})", f"No Warn\n({fn+tn})"]
        cols = [f"Wrong\n({wrongs})", f"Right\n({rights})"]
        
        sns.heatmap(matrix, annot=True, fmt='.0f', ax=axes[i], cmap="Purples",
                    xticklabels=cols, yticklabels=labels, cbar=False)
        axes[i].set_title(f"{cat} ({suffix})")

    plt.tight_layout()
    plt.savefig(os.path.join(path, f"{'9' if coding_only else '8'}_conf_matrix_{suffix}.png"), dpi=150)

def plot_10_warning_proportions(df, categories, path):
    suites = sorted(df['suite'].unique())
    think_cats = [c for c in categories if c != "Fast"]
    if not think_cats: return
    fig, ax = plt.subplots(figsize=(15, 8))
    x = np.arange(len(suites))
    width = 0.8 / len(think_cats)
    
    for i, cat in enumerate(think_cats):
        c_df = df[df['processing_type'] == cat]
        correct_rates, false_rates = [], []
        for s in suites:
            s_df = c_df[c_df['suite'] == s]
            total = s_df['repeats'].sum() or 1
            correct_rates.append((s_df['warning'].sum() - s_df['wrong_warnings'].sum()) / total)
            false_rates.append(-s_df['wrong_warnings'].sum() / total)

        offset = i * width - (len(think_cats)*width)/2 + width/2
        b1 = ax.bar(x + offset, correct_rates, width, label=f"{cat} (Correct)", color=sns.color_palette("viridis", 3)[i])
        b2 = ax.bar(x + offset, false_rates, width, label=f"{cat} (False)", color=sns.color_palette("flare", 3)[i], alpha=0.7)
        
        ax.bar_label(b1, fmt='%.2f', padding=3, fontsize=8)
        # For negative bars, show absolute value
        ax.bar_label(b2, labels=[f'{abs(v):.2f}' if v != 0 else '' for v in false_rates], padding=3, fontsize=8)

    ax.axhline(0, color='black', linewidth=1)
    ax.set_ylim(min(false_rates)*1.5 if false_rates else -0.5, 1.1)
    plt.xticks(x, [s.split(' ')[0] for s in suites], rotation=30)
    plt.legend(ncol=2)
    plt.tight_layout()
    plt.savefig(os.path.join(path, "10_warning_proportions.png"))

def plot_11_response_effectiveness(df, categories, path):
    plt.figure(figsize=(14, 7))
    def calc_eff(group):
        total = group['repeats'].sum()
        fp = group['wrong_warnings'].sum()
        tp = group['warning'].sum() - fp
        tn = group['success_count'].sum() - fp
        return (tn + tp) / total

    agg = df.groupby(['suite', 'processing_type']).apply(calc_eff).reset_index(name='eff')
    ax = sns.barplot(data=agg, x='suite', y='eff', hue='processing_type', hue_order=categories, palette='mako')
    
    for container in ax.containers:
        ax.bar_label(container, fmt='%.2f', padding=3, fontsize=9, weight='bold')

    plt.title("Model 'Honesty' Effectiveness (Correct + Self-Aware)")
    plt.ylim(0, 1.15)
    plt.xticks(rotation=30)
    plt.tight_layout()
    plt.savefig(os.path.join(path, "11_response_effectiveness.png"))

def plot_12_warning_impact(df, categories, path):
    """
    Wykres 12: Wpływ ostrzeżeń na efektywność (Delta Honesty).
    Delta = (Efektywność z ostrzeżeniami) - (Efektywność bez ostrzeżeń).
    Logika: Każde poprawne ostrzeżenie (TP) podnosi efektywność, 
    każde błędne ostrzeżenie (FP) ją obniża.
    """
    suites = sorted(df['suite'].unique())
    # Interesują nas tylko tryby agentyczne w konkretnej kolejności
    target_cats = ["Planning", "Chain_of_draft", "Reflection_refine"]
    active_cats = [c for c in target_cats if c in categories]
    
    if not active_cats:
        return

    fig, ax = plt.subplots(figsize=(15, 8))
    x = np.arange(len(suites))
    width = 0.8 / len(active_cats)

    # Paleta kolorów: odcienie niebieskiego/morskiego dla dodatnich, pomarańczu dla ujemnych
    # Ale dla spójności z legendą użyjemy stałych kolorów dla trybów
    colors = sns.color_palette("deep", len(active_cats))

    for i, cat in enumerate(active_cats):
        c_df = df[df['processing_type'] == cat]
        deltas = []
        
        for s in suites:
            s_df = c_df[c_df['suite'] == s]
            if s_df.empty:
                deltas.append(0)
                continue
            
            total_attempts = s_df['repeats'].sum()
            fp = s_df['wrong_warnings'].sum()           # Błędne ostrzeżenia (na poprawnej odpowiedzi)
            tp = s_df['warning'].sum() - fp             # Poprawne ostrzeżenia (na błędnej odpowiedzi)
            
            # Delta = (TP - FP) / Total
            # Wyjaśnienie: TP to zysk (wiemy o błędzie), FP to strata (podważamy prawdę)
            delta = (tp - fp) / total_attempts
            deltas.append(delta)

        offset = i * width - (len(active_cats)*width)/2 + width/2
        bars = ax.bar(x + offset, deltas, width, label=cat, color=colors[i], edgecolor='black', alpha=0.8)
        
        # Dodawanie etykiet z liczbami (razem ze znakiem)
        for bar in bars:
            height = bar.get_height()
            label = f'{height:+.2f}' if height != 0 else '0.00'
            ax.text(bar.get_x() + bar.get_width()/2., 
                    height + (0.01 if height >= 0 else -0.03),
                    label,
                    ha='center', va='bottom' if height >= 0 else 'top', 
                    fontsize=9, weight='bold')

    ax.axhline(0, color='black', linewidth=1.5)
    ax.set_title("Wpływ mechanizmu ostrzeżeń na wiarygodność modelu (Delta Effectiveness)\n" + 
                 "Zysk = TP (wykryte błędy), Strata = FP (fałszywe alarmy)", fontsize=14, pad=20)
    ax.set_ylabel("Zmiana efektywności (Delta SR)")
    ax.set_xticks(x)
    ax.set_xticklabels([s.split(' ')[0] for s in suites], rotation=30)
    
    # Siatka pomocnicza
    ax.yaxis.set_major_locator(MultipleLocator(0.1))
    ax.yaxis.set_minor_locator(MultipleLocator(0.05))
    ax.grid(which='major', axis='y', color='#CCCCCC', linestyle='--', alpha=0.7)
    
    ax.legend(title="Tryb agentyczny", loc='best')
    
    # Dynamiczne ustawienie limitów osi Y, aby napisy się nie ucinały
    ymin, ymax = ax.get_ylim()
    ax.set_ylim(ymin - 0.05, ymax + 0.05)

    plt.tight_layout()
    plt.savefig(os.path.join(path, "12_warning_impact_delta.png"), dpi=150)


def main():
    print("🚀 Starting analysis...")
    df, categories = apply_old_data()
    analysis_dir = get_next_analysis_path()
    print(f"📂 Saving results to: {analysis_dir}")

    # 0. Text Stats
    export_text_stats(df, categories, analysis_dir)
    
    # 1. General Heatmap
    plot_1_general_heatmap(df, categories, analysis_dir)
    
    # 2. Percentage Heatmap
    plot_2_percentage_heatmap(df, categories, analysis_dir)
    
    # 3. Bars by Suite
    plot_3_4_bar_charts(df, categories, analysis_dir, group_by='suite', filename="3_bars_by_suite.png")
    
    # 4. Bars by Intent
    intent_map = {1: 'Theory', 2: 'Coding', 3: 'CLI'}
    df['intent_name'] = df['intent'].map(intent_map)
    plot_3_4_bar_charts(df, categories, analysis_dir, group_by='intent_name', filename="4_bars_by_intent.png")
    
    # 5, 6, 7. Latency Analysis
    plot_5_6_7_latency_boxes(df, analysis_dir)

    print("🔍 Generating warning & effectiveness analysis (8-11)...")
    # 8. Confusion Matrix (All)
    plot_8_9_warning_confusion_matrices(df, categories, analysis_dir, coding_only=False)
    # 9. Confusion Matrix (Coding)
    plot_8_9_warning_confusion_matrices(df, categories, analysis_dir, coding_only=True)
    # 10. Proportions Up/Down
    plot_10_warning_proportions(df, categories, analysis_dir)
    # 11. Effectiveness
    plot_11_response_effectiveness(df, categories, analysis_dir)

    plot_12_warning_impact(df, categories, analysis_dir)

    print("✅ Analysis complete.")

if __name__ == "__main__":
    main()