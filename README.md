# Spotify MIR Toolkit

**Created by:** Tyler Bygrave  
**Module:** AMT6003 – Audio Programming (University Project)

## Overview

This application is a multi-functional desktop tool designed for Music Information Retrieval (MIR) research and education. It includes:

- A **Metadata Scraper** for Spotify playlists  
- A **Data Visualisation Suite** for playlist-level genre and popularity analysis  
- An **Audio Feature Viewer** for local audio files (WAV/MP3) with waveform, spectrogram, pitch-over-time, BPM, and key detection.

The tool was built using **Python**, with a focus on accessibility for beginners exploring MIR techniques.

---

## Features

### Home Screen
- Launch three independent modules:
  - `Metadata Collector`
  - `Data Analysis Tool`
  - `Audio Feature Viewer`

### Metadata Collector
- Scrapes Spotify playlist data (track names, artist genres, popularity, etc.)
- Exports playlist metadata as CSV for further analysis
- Includes progress bar and error handling

### Data Analysis Tool
- Imports and visualises multiple CSV or Excel files
- Word Cloud: Visualise genre/tag frequency across playlists
- Scatter Plot: Compare features (e.g. popularity vs release date)
- Genre Similarity Heatmap using Jaccard index

### Audio Feature Viewer
- Load a local audio file
- View:
  - **Waveform**
  - **Spectrogram**
  - **Pitch Over Time**
- Click to seek playback
- Automatically calculates:
  - BPM using Librosa’s beat tracking
  - Musical key using chromagram analysis
- Live red playback line synced with audio

---

## Requirements

- Python 3.9+
- Spotipy
- Librosa
- Numpy, Pandas
- SoundDevice
- Matplotlib
- Tkinter (usually included with Python)
- Wordcloud

You can install dependencies using:

```bash
pip install -r requirements.txt

## Notes on Security
Spotify CLIENT_ID and CLIENT_SECRET are currently hardcoded for academic testing.
In a production environment, consider using .env or environment variables to protect credentials.
