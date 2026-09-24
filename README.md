<p align="center">
  <img
    src="assets/images/logo_auracontent.png"
    alt="AuraContent Logo"
    width="160"
    height="160"
  />
</p>

<h1 align="center">🎬 AuraContent</h1>

<p align="center">
  <strong>Automated Faceless Video Generator and Publisher</strong>
</p>

<p align="center">
  Automatically create, edit, store, and publish short videos starting from a simple topic.
</p>

<p align="center">
  <img
    src="https://komarev.com/ghpvc/?username=SORADATA-AuraContent&style=for-the-badge&color=blue"
    alt="Visitor Count"
  />
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/FFmpeg-Enabled-007808?logo=ffmpeg&logoColor=white" alt="FFmpeg">
  <img src="https://img.shields.io/badge/GitHub_Actions-Automated-2088FF?logo=github-actions&logoColor=white" alt="GitHub Actions">
  <img src="https://img.shields.io/badge/Hugging_Face-Storage-FFD21E?logo=huggingface&logoColor=black" alt="Hugging Face">
  <img src="https://img.shields.io/badge/License-Open_Source-green" alt="License">
</p>

---

## 📌 Table of Contents

- [Overview](#-overview)
- [Features](#-features)
- [Pipeline Architecture](#-pipeline-architecture)
- [Project Structure](#-project-structure)
- [Prerequisites](#-prerequisites)
- [Secrets Configuration](#-secrets-configuration)
- [Installation with GitHub Actions](#-installation-with-github-actions)
- [Local Execution](#-local-execution)
- [Automated Scheduling](#-automated-scheduling)
- [Publishing Module](#-publishing-module)
- [Troubleshooting](#-troubleshooting)
- [Security Best Practices](#-security-best-practices)
- [License](#-license)

---

## 🚀 Overview

**AuraContent** is a Python pipeline designed to automate the creation and publication of short-form videos like **YouTube Shorts** or **TikToks**.

Starting from a single topic, the pipeline:

1. generates a script using Artificial Intelligence;
2. produces an audio voiceover;
3. searches for relevant stock videos;
4. assembles the different elements using FFmpeg;
5. stores the final video on Hugging Face;
6. automatically publishes the video to TikTok via the Zernio API.

The entire process can be executed in the cloud using **GitHub Actions**, requiring no dedicated server or always-on computer.

---

## ✨ Features

| Feature | Description |
|---|---|
| ☁️ **Cloud Automation** | Scheduled execution with GitHub Actions, requiring no dedicated server infrastructure. |
| 🧠 **Script Generation** | Creation of structured scripts using Google Gemini or Groq. |
| 🗣️ **Automated Voiceover** | Narration generation using `edge-tts`. |
| 🎞️ **Dual-Visual System** | Downloads two distinct stock videos per scene from Pexels. |
| ✂️ **Automated Editing** | Trimming, synchronization, transitions, and composition with FFmpeg. |
| 🤖 **Brand Avatar** | Random insertion of an avatar video in an intermediate scene. |
| 🤗 **Cloud Storage** | Secure storage of generated videos in a Hugging Face dataset. |
| 📱 **TikTok Publishing** | Automated publishing via the Zernio API. |
| 🛡️ **Anti-Duplication Protection** | Prevents publishing the same video multiple times. |
| 🏷️ **Auto Captions** | Generates a title and hashtags based on the video filename. |
| 🤖 **AI Content Disclosure** | Activates the `video_made_with_ai` setting during publication. |

---

## 🔄 Pipeline Architecture

```text
Topic
  │
  ▼
Script Generation
(Gemini or Groq)
  │
  ▼
Voiceover Generation
(edge-tts)
  │
  ▼
Stock Video Search
(Pexels)
  │
  ▼
Composition and Editing
(FFmpeg)
  │
  ▼
Final Video
  │
  ▼
Cloud Storage
(Hugging Face)
  │
  ▼
Automated Publishing
(Zernio → TikTok)
