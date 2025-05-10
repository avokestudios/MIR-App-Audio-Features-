import os
import glob
import csv
import threading
from datetime import datetime
from collections import defaultdict, Counter

import spotipy
from spotipy.oauth2 import SpotifyClientCredentials

import pandas as pd
import numpy as np

import librosa
import librosa.display
import sounddevice as sd

import tkinter as tk
from tkinter import filedialog, messagebox, ttk, scrolledtext

from ttkthemes import ThemedTk


import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend for image saving
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.animation import FuncAnimation
from wordcloud import WordCloud

# Global variable to store uploaded Excel file paths (if any)
uploaded_files = []

# ----------------------- METADATA APP FUNCTIONS ----------------------- #
CLIENT_ID = "206d3b06da384ae480d33a632e22a2a8"
CLIENT_SECRET = "d2ae0af919bc4064beec6a35070878fa"

def authenticate_spotify():
    client_credentials_manager = SpotifyClientCredentials(
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET
    )
    return spotipy.Spotify(client_credentials_manager=client_credentials_manager)

METADATA_FIELDS = [
    "track_name", "album_name", "release_date", "duration_ms",
    "track_spotify_url", "artist_name", "genres", "popularity",
    "followers", "artist_spotify_url"
]

def get_playlist_tracks(sp, playlist_id, progress_callback):
    tracks = []
    try:
        results = sp.playlist_tracks(playlist_id)
    except spotipy.exceptions.SpotifyException as e:
        messagebox.showerror("Spotify API Error", f"An error occurred: {e}")
        return []
    total = results.get("total", 0)
    count = 0
    while results:
        for item in results["items"]:
            track = item.get("track")
            if track:
                track_data = {
                    "track_name": track.get("name", "N/A"),
                    "album_name": track.get("album", {}).get("name", "N/A"),
                    "release_date": track.get("album", {}).get("release_date", "N/A"),
                    "duration_ms": track.get("duration_ms", "N/A"),
                    "track_spotify_url": track.get("external_urls", {}).get("spotify", "N/A"),
                    "artists": [artist["id"] for artist in track.get("artists", [])]
                }
                tracks.append(track_data)
            count += 1
            progress_callback(count, total)
        results = sp.next(results) if results.get("next") else None
    return tracks

def get_artist_metadata(sp, artist_ids):
    artists_data = {}
    batch_size = 50
    for i in range(0, len(artist_ids), batch_size):
        batch = artist_ids[i:i+batch_size]
        try:
            response = sp.artists(batch).get("artists", [])
            for artist in response:
                artists_data[artist["id"]] = {
                    "artist_name": artist.get("name", "N/A"),
                    "genres": ", ".join(artist.get("genres", [])),
                    "popularity": artist.get("popularity", "N/A"),
                    "followers": artist.get("followers", {}).get("total", 0),
                    "artist_spotify_url": artist.get("external_urls", {}).get("spotify", "N/A")
                }
        except Exception as e:
            print(f"Error fetching artist data: {e}")
    return artists_data

def collect_metadata(sp, playlist_id, progress_callback):
    tracks = get_playlist_tracks(sp, playlist_id, progress_callback)
    unique_artist_ids = {aid for t in tracks for aid in t["artists"]}
    artist_metadata = get_artist_metadata(sp, list(unique_artist_ids))
    final_data = []
    for track in tracks:
        for artist_id in track["artists"]:
            if artist_id in artist_metadata:
                entry = {
                    "track_name": track["track_name"],
                    "album_name": track["album_name"],
                    "release_date": track["release_date"],
                    "duration_ms": track["duration_ms"],
                    "track_spotify_url": track["track_spotify_url"],
                }
                entry.update(artist_metadata[artist_id])
                final_data.append(entry)
    return final_data

def export_to_csv(data, filename, playlist_name, playlist_owner):
    if not data:
        messagebox.showerror("Error", "No data to export.")
        return
    with open(filename, mode="w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(["Playlist Name", playlist_name])
        writer.writerow(["Playlist Owner", playlist_owner])
        writer.writerow(["Exported On", datetime.now().strftime("%Y-%m-%d")])
        writer.writerow([])
        writer.writerow(METADATA_FIELDS)
        for row in data:
            writer.writerow([row.get(field, "") for field in METADATA_FIELDS])
    messagebox.showinfo("Export Complete", f"Data successfully exported to:\n{filename}")

# ----------------------- DATA ANALYSIS FUNCTIONS ----------------------- #
def log_message(text_widget, message):
    text_widget.insert(tk.END, message + "\n")
    text_widget.see(tk.END)
    text_widget.update_idletasks()

def get_column_case_insensitive(df, col_name):
    for col in df.columns:
        if col.strip().lower() == col_name.strip().lower():
            return col
    return None

def load_data(folder_path, log_widget):
    global uploaded_files
    dfs = []
    if uploaded_files:
        log_message(log_widget, f"Loading {len(uploaded_files)} uploaded Excel file(s).")
        files_to_load = uploaded_files
    else:
        log_message(log_widget, f"Loading Excel files from folder: {folder_path}")
        files_to_load = glob.glob(os.path.join(folder_path, "*.xlsx"))

    if not files_to_load:
        log_message(log_widget, "No Excel files found.")
        return pd.DataFrame()

    for file in files_to_load:
        try:
            df = pd.read_excel(file, header=4, usecols="A:J")
            playlist_name = os.path.splitext(os.path.basename(file))[0]
            df["playlist"] = playlist_name
            dfs.append(df)
            log_message(log_widget, f"Loaded file: {os.path.basename(file)}")
        except Exception as e:
            log_message(log_widget, f"Error reading {file}: {e}")

    if dfs:
        combined_df = pd.concat(dfs, ignore_index=True)
        log_message(log_widget, f"Combined into {len(combined_df)} records.")
        return combined_df
    else:
        return pd.DataFrame()

# ----------------------- WORD CLOUD ----------------------- #
def create_word_cloud(df, output_dir, log_widget, genre_col_name, exported_filename):
    log_message(log_widget, f"Creating word cloud using column: '{genre_col_name}'...")
    selected_col = get_column_case_insensitive(df, genre_col_name)
    if not selected_col:
        log_message(log_widget, f"No column matching '{genre_col_name}' found.")
        messagebox.showerror("Error", f"No column '{genre_col_name}'")
        return

    word_counts = Counter()
    word_playlist = defaultdict(Counter)
    for _, row in df.iterrows():
        pl = row.get("playlist", "Unknown")
        cell = row[selected_col]
        if pd.isnull(cell):
            continue
        for w in [w.strip() for w in str(cell).split(",") if w.strip()]:
            word_counts[w] += 1
            word_playlist[w][pl] += 1

    if not word_counts:
        log_message(log_widget, f"Column '{selected_col}' is empty.")
        messagebox.showerror("Error", f"Column '{selected_col}' is empty")
        return

    word_to_playlist = {w: pl_counts.most_common(1)[0][0]
                        for w, pl_counts in word_playlist.items()}
    playlists = sorted(df["playlist"].dropna().unique())
    cmap = plt.get_cmap("tab10")
    colors = {pl: cmap(i % 10) for i, pl in enumerate(playlists)}

    def color_func(word, **kwargs):
        pl = word_to_playlist.get(word)
        return matplotlib.colors.rgb2hex(colors[pl]) if pl in colors else "black"

    wc = WordCloud(width=800, height=400, background_color="white")\
         .generate_from_frequencies(word_counts)
    wc.recolor(color_func=color_func)

    plt.figure(figsize=(12, 6))
    plt.imshow(wc, interpolation="bilinear")
    plt.axis("off")
    plt.title("Word Cloud (by Playlist)")
    handles = [Patch(color=matplotlib.colors.rgb2hex(colors[pl]), label=pl)
               for pl in playlists]
    plt.legend(handles=handles, title="Playlist", loc="center left",
               bbox_to_anchor=(1, 0.5))
    os.makedirs(output_dir, exist_ok=True)
    out_path = os.path.join(output_dir, exported_filename)
    plt.tight_layout(rect=[0, 0, 0.85, 1])
    plt.savefig(out_path)
    plt.close()
    log_message(log_widget, f"Word cloud saved to: {out_path}")

def process_and_visualise_word_cloud(folder_path, genre_col_name, wc_filename, log_widget):
    try:
        df = load_data(folder_path, log_widget)
        if df.empty:
            log_message(log_widget, "No data loaded. Exiting word cloud process.")
            return
        # place the output folder inside whichever you selected
        if uploaded_files:
            base = os.path.dirname(uploaded_files[0])
        else:
            base = folder_path
        output_dir = os.path.join(base, "output")
        os.makedirs(output_dir, exist_ok=True)
        create_word_cloud(df, output_dir, log_widget, genre_col_name, wc_filename)
        log_message(log_widget, "Word cloud processing complete. Check the output directory for the image.")
        messagebox.showinfo("Process Complete", "The word cloud image has been saved.")
    except Exception as e:
        log_message(log_widget, f"An error occurred (word cloud): {e}")
        messagebox.showerror("Error", str(e))

# ----------------------- SCATTER CHART ----------------------- #
def count_tags(val):
    if pd.isnull(val) or not str(val).strip():
        return 0
    return len([t.strip() for t in str(val).split(",") if t.strip()])

def transform_series(series, col_name):
    # If it looks like genres/tags, count commas
    if "genre" in col_name.lower() or "tag" in col_name.lower():
        return series.apply(count_tags)
    # Try numeric first
    numeric = pd.to_numeric(series, errors="coerce")
    if not numeric.isna().all():
        return numeric
    # Fallback: parse dates in any common format
    return pd.to_datetime(series, errors="coerce", format="%Y-%m-%d")



def create_scatter_chart(df, output_dir, log_widget,
                         x_col_name, y_col_name,
                         exported_filename,
                         group_col="playlist"):

    log_message(log_widget, f"Scatter: X='{x_col_name}' Y='{y_col_name}'")
    x_raw = df[get_column_case_insensitive(df, x_col_name)]
    y_raw = df[get_column_case_insensitive(df, y_col_name)]
    if x_raw is None or y_raw is None or group_col not in df.columns:
        messagebox.showerror("Error", "Columns missing.")
        return

    df["xv"] = transform_series(x_raw, x_col_name)
    df["yv"] = transform_series(y_raw, y_col_name)

    groups = sorted(df[group_col].dropna().unique())
    cmap = plt.get_cmap("tab10")
    colors = {g: cmap(i % 10) for i, g in enumerate(groups)}
    markers = ['o','s','^','D','P','X','*','v','<','>','H']

    plt.figure(figsize=(12, 8))
    for i, grp in enumerate(groups):
        sub = df[df[group_col] == grp]
        plt.scatter(sub["xv"], sub["yv"],
                    color=colors[grp],
                    marker=markers[i % len(markers)],
                    label=grp,
                    alpha=0.7,
                    edgecolors='w',
                    linewidth=0.5,
                    s=50)

    plt.xlabel(x_col_name)
    plt.ylabel(y_col_name)
    plt.title(f"{y_col_name} vs {x_col_name}")
    plt.grid(linestyle='--', alpha=0.5)

    if "tag" in x_col_name.lower() or "genre" in x_col_name.lower():
        ticks = sorted(df["xv"].dropna().unique())
        plt.xticks(ticks)

    handles = [Patch(color=matplotlib.colors.rgb2hex(colors[g]), label=g)
               for g in groups]
    plt.legend(handles=handles, title=group_col,
               bbox_to_anchor=(1.05,1), loc="upper left")

    os.makedirs(output_dir, exist_ok=True)
    out_path = os.path.join(output_dir, exported_filename)
    plt.tight_layout()
    plt.savefig(out_path, dpi=300)
    plt.close()

    log_message(log_widget, f"Scatter graph saved to: {out_path}")

def process_and_visualize_scatter(folder_path, x_col_name, y_col_name, sg_filename, log_widget):
    try:
        df = load_data(folder_path, log_widget)
        if df.empty:
            log_message(log_widget, "No data loaded. Exiting scatter graph process.")
            return
        # same output logic
        if uploaded_files:
            base = os.path.dirname(uploaded_files[0])
        else:
            base = folder_path
        output_dir = os.path.join(base, "output")
        os.makedirs(output_dir, exist_ok=True)
        create_scatter_chart(df, output_dir, log_widget, x_col_name, y_col_name, sg_filename)
        log_message(log_widget, "Scatter graph processing complete. Check the output directory for the image.")
        messagebox.showinfo("Process Complete", "The scatter graph image has been saved.")
    except Exception as e:
        log_message(log_widget, f"An error occurred (scatter graph): {e}")
        messagebox.showerror("Error", str(e))

# -------------------- GENRE SIMILARITY FUNCTION -------------------- #
def compute_genre_similarity_and_plot(df, genre_col='genres', output_dir="./output"):
    import itertools, os
    from collections import defaultdict
    from matplotlib import pyplot as plt

    if genre_col not in df.columns:
        print(f"Column {genre_col} not found.")
        return

    # 1) build per‐track genre sets
    genre_sets = []
    for gs in df[genre_col].fillna("").tolist():
        s = {g.strip() for g in gs.split(",") if g.strip()}
        if s:
            genre_sets.append(s)

    # 2) compute all pairwise Jaccard scores
    jaccard_scores = []
    for i in range(len(genre_sets)):
        for j in range(i+1, len(genre_sets)):
            a, b = genre_sets[i], genre_sets[j]
            inter = len(a & b)
            union = len(a | b)
            if union:
                jaccard_scores.append(inter/union)
    avg_jaccard = sum(jaccard_scores)/len(jaccard_scores) if jaccard_scores else 0

    # 3) build co‐occurrence counts
    co_occ = defaultdict(int)
    all_genres = set().union(*genre_sets)
    for s in genre_sets:
        for x, y in itertools.combinations(sorted(s), 2):
            co_occ[(x,y)] += 1

    genres = sorted(all_genres)
    idx = {g:i for i,g in enumerate(genres)}
    mat = [[0]*len(genres) for _ in genres]
    for (x,y), cnt in co_occ.items():
        i,j = idx[x], idx[y]
        mat[i][j] = mat[j][i] = cnt

    # 4) plot heatmap
    fig, ax = plt.subplots(figsize=(10,8))
    cax = ax.matshow(mat, cmap='viridis')
    fig.colorbar(cax)
    ax.set_xticks(range(len(genres)))
    ax.set_yticks(range(len(genres)))
    ax.set_xticklabels(genres, rotation=90)
    ax.set_yticklabels(genres)
    plt.title(f"Genre Co-occurrence Heatmap\nAvg. Jaccard: {avg_jaccard:.2f}")

    os.makedirs(output_dir, exist_ok=True)


    path = os.path.join(output_dir, "genre_similarity_heatmap.png")
    plt.tight_layout()
    plt.savefig(path)
    plt.close()

    return avg_jaccard, path



# -------------------- ANALYSIS TABS -------------------- #
def add_genre_similarity_tab(notebook, log_text):
    frame = tk.Frame(notebook)
    notebook.add(frame, text="Genre Similarity")

    tk.Label(frame, text="Folder / Uploaded Files:", font=("Arial", 10)).pack(pady=5)
    fld = tk.Entry(frame, width=50, font=("Arial", 10))
    fld.pack(pady=5)
    tk.Button(frame, text="Browse Folder", command=lambda: fld.insert(0, filedialog.askdirectory())).pack(pady=5)
    tk.Label(frame, text="Shows which genres co-occur across tracks.\nProduces a heatmap of co-occurrence counts.",
             font=("Arial", 9), fg="gray", wraplength=700, justify="left").pack(pady=5)

    def run_analysis():
        folder = fld.get()
        df = load_data(folder, log_text)
        if df.empty:
            log_message(log_text, "No data loaded.")
            return

        # use the same output folder convention
        if uploaded_files:
            base = os.path.dirname(uploaded_files[0])
        else:
            base = folder
        output_dir = os.path.join(base, "output")
        os.makedirs(output_dir, exist_ok=True)

        avg, path = compute_genre_similarity_and_plot(df, genre_col='genres', output_dir=output_dir)
        log_message(log_text, f"Avg. Jaccard Similarity: {avg:.2f}")
        log_message(log_text, f"Heatmap saved to: {path}")
        messagebox.showinfo(
            "Genre Similarity",
            f"Analysis complete.\nAvg. Jaccard: {avg:.2f}\nSaved to: {path}"
        )


    tk.Button(frame, text="Run Analysis", font=("Arial", 10, "bold"),
              command=run_analysis).pack(pady=10)

def add_release_vs_popularity_tab(notebook, log_text):
    frame = tk.Frame(notebook)
    notebook.add(frame, text="Release vs Popularity")

    tk.Label(frame, text="Folder / Uploaded Files:", font=("Arial", 10)).pack(pady=5)
    fld = tk.Entry(frame, width=50, font=("Arial", 10))
    fld.pack(pady=5)
    tk.Button(frame, text="Browse Folder", command=lambda: fld.insert(0, filedialog.askdirectory())).pack(pady=5)
    tk.Label(frame, text="Plots each track’s release date against its popularity.\nGenerates a scatter chart.",
             font=("Arial", 9), fg="gray", wraplength=700, justify="left").pack(pady=5)

    def run_scatter():
        df = load_data(fld.get(), log_text)
        if df.empty:
            log_message(log_text, "No data loaded.")
            return
        out = os.path.join(os.path.dirname(fld.get()), "output")
        os.makedirs(out, exist_ok=True)
        create_scatter_chart(df, out, log_text,
                             "release_date","popularity",
                             "release_vs_popularity.png")
        messagebox.showinfo("Done", "Scatter saved to output folder")

    tk.Button(frame, text="Generate Scatter", font=("Arial", 10, "bold"),
              command=run_scatter).pack(pady=10)

# ----------------------- UI LAUNCH FUNCTIONS ----------------------- #
def run_metadata_app():
    meta_window = tk.Toplevel(root)
    meta_window.title("Spotify Playlist Metadata Scraper")
    meta_window.geometry("900x400")
    meta_window.resizable(False, False)
    meta_window.configure(bg="#121212")

    tk.Label(meta_window, text="Spotify Playlist Metadata Scraper",
             font=("Arial", 18, "bold"), fg="white", bg="#121212")\
      .pack(pady=10)

    frame = tk.Frame(meta_window, bg="#121212")
    frame.pack(pady=20)

    tk.Label(frame, text="Enter Playlist ID/URL:",
             font=("Arial", 12), fg="white", bg="#121212")\
      .pack(side="left", padx=5)
    entry = tk.Entry(frame, width=45, font=("Arial", 12),
                     bg="#1E1E1E", fg="white", insertbackground="white")
    entry.pack(side="left", padx=10)

    progress_var = tk.IntVar(meta_window)
    progress_bar = ttk.Progressbar(meta_window, variable=progress_var,
                                   maximum=100, length=400, mode="determinate")
    progress_bar.pack(pady=(10,0))

    status_label = tk.Label(meta_window, text="Ready",
                            font=("Arial", 12), fg="white", bg="#121212")
    status_label.pack(pady=5)

    def update_progress(current, total):
        if total>0:
            pct = int((current/total)*100)
            if 0 <= pct <= 100:
                progress_var.set(pct)
                progress_bar.update_idletasks()

    def run_scraper():
        pid = entry.get().strip()
        if not pid:
            messagebox.showerror("Error","Please enter a playlist ID")
            return
        def scrape():
            status_label.config(text="Fetching data...", fg="#FFC107")
            btn.config(state="disabled")
            progress_bar.start(10)
            try:
                sp = authenticate_spotify()
                info = sp.playlist(pid)
                data = collect_metadata(sp, pid, update_progress)
                progress_bar.stop()
                status_label.config(text="Ready", fg="#4CAF50")
                btn.config(state="normal")
                ts = datetime.now().strftime("%Y-%m-%d")
                fname = f"{info['name']} - {info['owner']['display_name']} - {ts}.csv".replace("/","_")
                folder = filedialog.askdirectory(title="Select folder to save CSV")
                if folder:
                    export_to_csv(data, os.path.join(folder, fname),
                                  info["name"], info["owner"]["display_name"])
            except Exception as e:
                progress_bar.stop()
                status_label.config(text="Error", fg="#F44336")
                btn.config(state="normal")
                messagebox.showerror("Error", f"{e}")

        threading.Thread(target=scrape, daemon=True).start()

    btn = tk.Button(frame, text="Scrape Metadata", font=("Arial",12,"bold"),
                    bg="#1DB954", fg="white", command=run_scraper)
    btn.pack(side="right", padx=5)

def run_data_analysis_app():
    # ——— Create the analysis window ———
    analysis_window = tk.Toplevel(root)
    analysis_window.title("Metadata Visualiser")
    analysis_window.geometry("800x700")

    # ——— Menu bar ———
    menu_bar = tk.Menu(analysis_window)
    file_menu = tk.Menu(menu_bar, tearoff=0)

    def upload_files():
        global uploaded_files
        files = filedialog.askopenfilenames(
            title="Select Excel Files",
            filetypes=[("Excel files","*.xlsx")]
        )
        if files:
            uploaded_files = list(files)
            folder_entry.delete(0, tk.END)
            folder_entry.insert(0, "Uploaded Excel Files")
            log_message(log_text, f"Uploaded {len(files)} file(s).")

    def browse_folder():
        global uploaded_files
        uploaded_files = []
        folder = filedialog.askdirectory(
            title="Select Folder Containing Excel Files"
        )
        if folder:
            folder_entry.delete(0, tk.END)
            folder_entry.insert(0, folder)
            log_message(log_text, f"Selected folder: {folder}")

    file_menu.add_command(label="Upload Excel Files", command=upload_files)
    file_menu.add_command(label="Browse Folder",       command=browse_folder)
    file_menu.add_separator()
    file_menu.add_command(label="Exit",                command=analysis_window.destroy)
    menu_bar.add_cascade(label="File", menu=file_menu)
    analysis_window.config(menu=menu_bar)

    # ——— Notebook for tabs ———
    notebook = ttk.Notebook(analysis_window)

    # ——— Word Cloud Tab ———
    word_cloud_frame = tk.Frame(notebook)
    notebook.add(word_cloud_frame, text="Word Cloud")

    folder_frame = tk.Frame(word_cloud_frame)
    folder_frame.pack(pady=10)
    tk.Label(folder_frame, text="Folder / Uploaded Files:", font=("Arial",10))\
      .pack(side="left", padx=5)
    folder_entry = tk.Entry(folder_frame, width=50, font=("Arial",10))
    folder_entry.pack(side="left", padx=5)
    tk.Button(folder_frame, text="Browse", command=browse_folder)\
      .pack(side="left", padx=5)

    wc_config_frame = tk.Frame(word_cloud_frame)
    wc_config_frame.pack(pady=5)
    tk.Label(wc_config_frame, text="Genre Column:", font=("Arial",10))\
      .grid(row=0, column=0, padx=5, pady=2, sticky="e")
    wc_entry = tk.Entry(wc_config_frame, width=15, font=("Arial",10))
    wc_entry.grid(row=0, column=1, padx=5, pady=2)
    wc_entry.insert(0, "genres")
    tk.Label(wc_config_frame, text="Export Filename:", font=("Arial",10))\
      .grid(row=0, column=2, padx=5, pady=2, sticky="e")
    wc_filename_entry = tk.Entry(wc_config_frame, width=15, font=("Arial",10))
    wc_filename_entry.grid(row=0, column=3, padx=5, pady=2)
    wc_filename_entry.insert(0, "word_cloud.png")
    tk.Button(
        word_cloud_frame,
        text="Generate Word Cloud",
        font=("Arial",10),
        command=lambda: process_and_visualise_word_cloud(
            folder_entry.get(),
            wc_entry.get(),
            wc_filename_entry.get(),
            log_text
        )
    ).pack(pady=10)

    # ——— Scatter Graph Tab ———
    scatter_frame = tk.Frame(notebook)
    notebook.add(scatter_frame, text="Scatter Graph")

    folder_frame2 = tk.Frame(scatter_frame)
    folder_frame2.pack(pady=10)
    tk.Label(folder_frame2, text="Folder / Uploaded Files:", font=("Arial",10))\
      .pack(side="left", padx=5)
    folder_entry2 = tk.Entry(folder_frame2, width=50, font=("Arial",10))
    folder_entry2.pack(side="left", padx=5)
    tk.Button(folder_frame2, text="Browse", command=browse_folder)\
      .pack(side="left", padx=5)

    sg_config_frame = tk.Frame(scatter_frame)
    sg_config_frame.pack(pady=5)
    tk.Label(sg_config_frame, text="X Axis Column:", font=("Arial",10))\
      .grid(row=0, column=0, padx=5, pady=2, sticky="e")
    x_entry = tk.Entry(sg_config_frame, width=15, font=("Arial",10))
    x_entry.grid(row=0, column=1, padx=5, pady=2)
    x_entry.insert(0, "tags")
    tk.Label(sg_config_frame, text="Y Axis Column:", font=("Arial",10))\
      .grid(row=1, column=0, padx=5, pady=2, sticky="e")
    y_entry = tk.Entry(sg_config_frame, width=15, font=("Arial",10))
    y_entry.grid(row=1, column=1, padx=5, pady=2)
    y_entry.insert(0, "followers")
    tk.Label(sg_config_frame, text="Export Filename:", font=("Arial",10))\
      .grid(row=2, column=0, padx=5, pady=2, sticky="e")
    sg_filename_entry = tk.Entry(sg_config_frame, width=15, font=("Arial",10))
    sg_filename_entry.grid(row=2, column=1, padx=5, pady=2)
    sg_filename_entry.insert(0, "scatter_graph.png")
    tk.Button(
        scatter_frame,
        text="Generate Scatter Graph",
        font=("Arial",10),
        command=lambda: process_and_visualise_scatter(
            folder_entry2.get(),
            x_entry.get(),
            y_entry.get(),
            sg_filename_entry.get(),
            log_text
        )
    ).pack(pady=10)

    # ——— Instantiate log_text **before** adding tabs that refer to it ———
    log_text = scrolledtext.ScrolledText(
        analysis_window,
        width=90,
        height=10,
        font=("Arial",10),
        state="normal"
    )
    log_text.pack(pady=10)

    # ——— Now safe to add your custom tabs ———
    add_genre_similarity_tab(notebook, log_text)
    add_release_vs_popularity_tab(notebook, log_text)

    # ——— Pack the notebook ———
    notebook.pack(pady=10, fill="both", expand=True)

    # ——— Clear‐log button ———
    tk.Button(
        analysis_window,
        text="Clear Log",
        font=("Arial",10),
        command=lambda: log_text.delete(1.0, tk.END)
    ).pack(pady=5)

    # -------------- Audio Feature App ------------------- #

def run_audio_feature_app():
    import matplotlib.pyplot as plt
    import librosa.display
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    from matplotlib.animation import FuncAnimation
    import sounddevice as sd
    import numpy as np
    import librosa

    np.complex = complex  # For compatibility with older code using np.complex

    audio_window = tk.Toplevel()
    audio_window.title("Audio Feature Viewer")
    audio_window.geometry("900x700")

    filepath_entry = tk.Entry(audio_window, width=80)
    filepath_entry.pack(pady=5)

    dropdown_var = tk.StringVar()
    dropdown_menu = ttk.Combobox(audio_window, textvariable=dropdown_var, state="readonly")
    dropdown_menu['values'] = ("Waveform", "Spectrogram", "Pitch Over Time")
    dropdown_menu.current(0)
    dropdown_menu.pack(pady=5)

    bpm_label = tk.Label(audio_window, text="BPM: Not calculated", font=("Arial", 10), fg="blue")
    bpm_label.pack()

    key_label = tk.Label(audio_window, text="Key: Not calculated", font=("Arial", 10), fg="blue")
    key_label.pack()

    duration_label = tk.Label(audio_window, text="Duration: N/A", font=("Arial", 10))
    duration_label.pack()

    pitch_label = tk.Label(audio_window, text="Current Pitch: N/A", font=("Arial", 10))
    pitch_label.pack()

    status_label = tk.Label(audio_window, text="", font=("Arial", 9), fg="gray")
    status_label.pack()

    canvas_frame = tk.Frame(audio_window, width=900, height=350)
    canvas_frame.pack(pady=5, fill="both", expand=False)

    btn_frame = tk.Frame(audio_window)
    btn_frame.pack(pady=10)

    audio_data = None
    sample_rate = None
    duration = None
    is_playing = False
    current_view = "Waveform"
    red_line = None
    canvas = None
    fig, ax = None, None
    animation = None
    pitch_times, pitch_freqs = None, None

    def clear_canvas():
        for widget in canvas_frame.winfo_children():
            widget.destroy()
        plt.close('all')  # Important to prevent figure buildup

    def draw_static_plot():
        nonlocal fig, ax, canvas, pitch_times, pitch_freqs
        clear_canvas()

        fig, ax = plt.subplots(figsize=(8, 3), dpi=100)

        if current_view == "Waveform":
            librosa.display.waveshow(audio_data, sr=sample_rate, ax=ax)
            ax.set_title("Waveform (click to seek)")
            ax.set_ylabel("Amplitude")

        elif current_view == "Spectrogram":
            D = librosa.amplitude_to_db(np.abs(librosa.stft(audio_data)), ref=np.max)
            librosa.display.specshow(D, sr=sample_rate, x_axis='time', y_axis='log', ax=ax)
            ax.set_title("Spectrogram")
            ax.set_ylabel("Frequency (Hz)")

        elif current_view == "Pitch Over Time":
            pitches, magnitudes = librosa.piptrack(y=audio_data, sr=sample_rate)
            pitch_times = librosa.frames_to_time(np.arange(pitches.shape[1]), sr=sample_rate)
            pitch_freqs = []
            for i in range(pitches.shape[1]):
                magn = magnitudes[:, i]
                pitch = pitches[:, i]
                if np.any(magn > np.median(magn)):
                    pitch_freqs.append(np.mean(pitch[magn > np.median(magn)]))
                else:
                    pitch_freqs.append(0)
            ax.plot(pitch_times, pitch_freqs, color='green')
            ax.set_title("Pitch Over Time")
            ax.set_ylabel("Frequency (Hz)")

        ax.set_xlabel("Time (s)")
        fig.tight_layout()

        canvas = FigureCanvasTkAgg(fig, master=canvas_frame)
        canvas.draw()
        canvas.get_tk_widget().pack(fill="both", expand=True)

        def on_click(event):
            if event.inaxes and audio_data is not None:
                t = event.xdata
                if t:
                    i = int(t * sample_rate)
                    sd.stop()
                    sd.play(audio_data[i:], samplerate=sample_rate)
                    update_red_line(t)
                    status_label.config(text=f"Playing from {t:.2f} seconds")

        fig.canvas.mpl_connect("button_press_event", on_click)

    def update_red_line(x):
        nonlocal red_line
        if red_line:
            red_line.remove()
        red_line = ax.axvline(x=x, color='red', linestyle='--')
        canvas.draw_idle()

    def animate_red_line():
        def update(frame):
            if is_playing and sd.get_stream().active:
                t = sd.get_stream().time
                update_red_line(t)
                if current_view == "Pitch Over Time" and pitch_times is not None:
                    idx = np.argmin(np.abs(pitch_times - t))
                    current_pitch = pitch_freqs[idx] if 0 <= idx < len(pitch_freqs) else 0
                    if current_pitch > 0:
                        pitch_label.config(text=f"Current Pitch: {current_pitch:.2f} Hz")
            return ax

        return FuncAnimation(fig, update, interval=100)

    def browse_file():
        nonlocal audio_data, sample_rate, duration, is_playing

        path = filedialog.askopenfilename(filetypes=[("Audio Files", "*.wav *.mp3")])
        if not path:
            return

        try:
            filepath_entry.delete(0, tk.END)
            filepath_entry.insert(0, path)
            bpm_label.config(text="BPM: Not calculated")
            pitch_label.config(text="Current Pitch: N/A")
            key_label.config(text="Key: Not calculated")
            duration_label.config(text="Duration: N/A")
            status_label.config(text="Loading audio...")

            y, sr = librosa.load(path, sr=None)
            audio_data = y
            sample_rate = sr
            duration = librosa.get_duration(y=y, sr=sr)
            duration_label.config(text=f"Duration: {duration:.2f} seconds")

            draw_static_plot()
            status_label.config(text="Audio loaded.")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load audio:\n{e}")
            status_label.config(text="")

    def toggle_play_pause():
        nonlocal is_playing, animation
        if audio_data is None:
            messagebox.showerror("Error", "No audio loaded.")
            return
        if not is_playing:
            sd.play(audio_data, samplerate=sample_rate)
            is_playing = True
            status_label.config(text="Playing...")
            animation = animate_red_line()
        else:
            sd.stop()
            is_playing = False
            status_label.config(text="Paused.")

    def stop_audio():
        nonlocal is_playing
        sd.stop()
        is_playing = False
        status_label.config(text="Stopped.")

    def calculate_bpm():
        if audio_data is None:
            messagebox.showerror("Error", "No audio loaded.")
            return
        tempo, _ = librosa.beat.beat_track(y=audio_data, sr=sample_rate)
        bpm_val = float(tempo) if np.isscalar(tempo) else float(tempo[0])
        bpm_label.config(text=f"BPM: {bpm_val:.2f}")

    def calculate_key():
        if audio_data is None:
            messagebox.showerror("Error", "No audio loaded.")
            return
        chroma = librosa.feature.chroma_cqt(y=audio_data, sr=sample_rate)
        chroma_mean = np.mean(chroma, axis=1)
        key_idx = np.argmax(chroma_mean)
        keys = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
        key_label.config(text=f"Key: {keys[key_idx]} major")

    def refresh_view(*args):
        nonlocal current_view
        current_view = dropdown_var.get()
        if audio_data is not None:
            draw_static_plot()

    dropdown_var.trace('w', refresh_view)

    # Buttons
    tk.Button(btn_frame, text="Browse", command=browse_file, width=15).grid(row=0, column=0, padx=5)
    tk.Button(btn_frame, text="Play/Pause", command=toggle_play_pause, width=15).grid(row=0, column=1, padx=5)
    tk.Button(btn_frame, text="Stop Audio", command=stop_audio, width=15).grid(row=0, column=2, padx=5)
    tk.Button(btn_frame, text="Calculate BPM", command=calculate_bpm, width=18).grid(row=0, column=3, padx=5)
    tk.Button(btn_frame, text="Detect Key", command=calculate_key, width=15).grid(row=0, column=4, padx=5)


# ----------------------- HOME PAGE ----------------------- #
root = tk.Tk()
root.title("Spotify MIR Home")
root.geometry("700x250")
root.configure(bg="#1ED760")
root.resizable(False, False)
root.protocol("WM_DELETE_WINDOW", root.destroy)

home_label = tk.Label(root, text="Select a Tool to Launch",
                      background="#1DB954", foreground="white",
                      font=("Helvetica",18,"bold"))
home_label.pack(pady=20)

button_frame = tk.Frame(root, bg="#1DB954")
button_frame.pack(pady=10)

meta_button = tk.Button(button_frame, text="Metadata Collector",
                        font=("Arial",12), width=20,
                        command=run_metadata_app)
meta_button.grid(row=0, column=0, padx=10, pady=10)

analysis_button = tk.Button(button_frame, text="Data Analysis Tool",
                            font=("Arial",12), width=20,
                            command=run_data_analysis_app)
analysis_button.grid(row=0, column=1, padx=10, pady=10)

audio_button = tk.Button(button_frame, text="Audio Feature Viewer",
                         font=("Arial", 12), width=20,
                         command=run_audio_feature_app)

audio_button.grid(row=1, column=0, columnspan=2, pady=10)


root.mainloop()