You are an expert technical presentation designer and AI consultant. Please generate a highly professional, visually engaging PowerPoint presentation structure and content for my project titled **"Multimodal AI-Agent for AQI Health Risk Analysis"**.

Using the detailed project context provided below, generate the exact slide-by-slide content, speaker notes, and suggestions for visuals/diagrams. Make sure the tone is academic yet accessible, suitable for a capstone project or technical product pitch.

### 📌 Required Slide Structure:
1. **Title Slide**: Title, Subtitle, and Group Members Info.
2. **Introduction**: Current issues regarding air quality, motivation behind the project, and our main objective.
3. **Problem Statement**: The core problem, challenges in existing methods, and our proposed AI-driven solution.
4. **Literature Survey / Comparative Analysis**: Comparing current existing systems (e.g., standard AQI apps) with our personalized, multi-pollutant solution.
5. **Process Flow**: Step-by-step workflow with a detailed description for a process flow diagram.
6. **Architecture Diagram**: Explanation of the Multi-Agent system architecture (Orchestrator, Data Agent, Health Agent, Viz Agent, GIS Agent).
7. **Technology Stack**: Full list of tools, frameworks, and APIs used.
8. **Dataset Details**: Data sources, types of pollutants, and real-time APIs utilized.
9. **Papers & Guidelines Referred**: Medical and environmental standards (WHO, CPCB, EPA).
10. **References**: APIs, frameworks, and scientific bases.
11. **Thank You Slide**: Q&A and closing.

---

### 🧠 Project Context & Technical Details:

**Project Overview:**
Standard weather and AQI apps only provide a single generalized number (e.g., "AQI 150"). This project is a Multi-Agent AI System that provides personalized health risk intelligence. It calculates dynamic hazard indexes, detects pollutant synergies, and adjusts risk scores based on a user's persona (e.g., Asthma patient, Athlete, Elderly), activity level (resting vs. vigorous), and environment (indoor vs. outdoor).

**Key Features & Differentiators:**
- **Multi-Pollutant Risk Score (MPRS):** Instead of just taking the highest pollutant, it calculates a weighted score across PM2.5, PM10, NO2, SO2, CO, and O3, applying different weights based on the user's vulnerability.
- **Pollutant Synergy Detection:** Detects dangerous combinations (e.g., PM2.5 + O3) that exponentially increase oxidative stress and airway inflammation.
- **Hazard Index (HI):** Uses the WHO cumulative risk formula `HI = Σ (Concentration / Limit)` to warn about the "cocktail effect" of multiple pollutants.
- **Exposure Modeling:** Calculates the inhaled dose of pollutants based on the user's ventilation rate (Activity Level: Resting, Light, Moderate, Vigorous).
- **24-Hour Risk Timeline:** Forecasts optimal safe windows for outdoor activities.

**Architecture (Multi-Agent System):**
1. **Orchestrator Agent:** The central brain. Parses natural language queries (e.g., "Is it safe to run outside for an asthma patient?"), extracts entities, and delegates tasks.
2. **Data Agent:** Scrapes and fetches real-time atmospheric data. Fallback mechanism uses WAQI for base AQI and Open-Meteo for exact real-time µg/m³ concentrations. It calculates CPCB-standard AQI.
3. **Health Agent:** The medical reasoning engine. Computes the MPRS, Hazard Index, Synergy Warnings, and tailored Mask usage recommendations.
4. **Visualization Agent:** Generates interactive Plotly charts (Historical trends, 24-hr Risk Timelines, Persona Risk Comparisons).
5. **GIS Agent:** Handles spatial data, generating Folium-based interactive heatmaps and pollutant radius checks.

**Technology Stack:**
- **Frontend/UI:** Streamlit
- **Visualization:** Plotly, Folium (Maps)
- **Data Manipulation:** Pandas, NumPy
- **Agent Communication:** Pydantic (data schemas), Python
- **APIs & Data Sources:** WAQI (World Air Quality Index), Open-Meteo Air Quality API, OpenWeatherMap, web scraping (aqi.in), CPCB (Central Pollution Control Board) standards.
- **AI/NLP Layer:** Rule-based NLP extraction and intent classification (currently), designed to integrate with LLMs.

**Scientific Foundation (Literature & Guidelines):**
- **WHO Air Quality Guidelines (2021):** Used for hazard index limits (e.g., PM2.5 annual mean limits).
- **Indian CPCB Standards:** Used for linear interpolation of raw µg/m³ concentrations into categorized AQI.
- **US EPA:** Synergistic effects of O3 and PM.
- **Medical research:** Ventilation rates during exercise mapping to increased pulmonary deposition of particulate matter.

---
**Task for Chronicles AI:**
Generate the slide content exactly matching the 11 required slides. For slides requiring diagrams (Architecture & Process Flow), provide a highly descriptive prompt or Mermaid.js code that can be used to generate the visual. Ensure bullet points are concise (rule of 6x6 if possible) and speaker notes are provided for each slide.
