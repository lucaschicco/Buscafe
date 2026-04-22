#!/usr/bin/env python
# coding: utf-8

import dash
from dash import dcc, html
from dash.dependencies import Input, Output, State
import dash_leaflet as dl
import pandas as pd
from dash_extensions.javascript import assign
#import dash_bootstrap_components as dbc
import numpy as np
from flask_compress import Compress
import json
import requests
from azure.storage.blob import BlobServiceClient
import os
from datetime import datetime
import orjson
import unicodedata
from dotenv import load_dotenv
from flask import Response
import re

# Cargar variables de entorno desde .env en desarrollo
# En Azure esto no hace nada porque las variables ya vienen del sistema
load_dotenv()

# Configuración de Firebase desde variables de entorno
FIREBASE_CONFIG = {
    'apiKey': os.getenv('FIREBASE_API_KEY'),
    'authDomain': os.getenv('FIREBASE_AUTH_DOMAIN'),
    'projectId': os.getenv('FIREBASE_PROJECT_ID'),
    'storageBucket': os.getenv('FIREBASE_STORAGE_BUCKET'),
    'messagingSenderId': os.getenv('FIREBASE_MESSAGING_SENDER_ID'),
    'appId': os.getenv('FIREBASE_APP_ID')
}



# Convertir a JSON string para inyectar en templates
FIREBASE_CONFIG_JSON = json.dumps(FIREBASE_CONFIG)

app = dash.Dash(__name__, title="Buscafes")
server = app.server  # Esto expone el servidor de Flask


@server.route('/api/geojson')
def serve_geojson():
    return Response(
        orjson.dumps(geojson_data),  # orjson ya lo tenés importado
        mimetype='application/json',
        headers={'Cache-Control': 'public, max-age=3600'}  # cachea 1h en browser
    )



# ════════════════════════════════════════════════════════════
# PÁGINAS LEGALES (para Google OAuth verification)
# ════════════════════════════════════════════════════════════
@server.route('/privacidad')
def privacidad():
    return '''
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <title>Política de Privacidad - Buscafes</title>
        <style>
            body { font-family: 'Montserrat', Arial, sans-serif; max-width: 800px; margin: 50px auto; padding: 20px; line-height: 1.6; }
            h1 { color: #104547; }
            a { color: #104547; }
        </style>
    </head>
    <body>
        <h1>Política de Privacidad</h1>
        <p><strong>Última actualización:</strong> Febrero 2026</p>
        
        <h2>Información que recopilamos</h2>
        <p>Buscafes recopila únicamente tu dirección de correo electrónico y nombre de perfil 
        cuando iniciás sesión con Google. Estos datos se utilizan exclusivamente para:</p>
        <ul>
            <li>Identificarte dentro de la aplicación</li>
            <li>Guardar tus cafeterías favoritas y visitadas</li>
            <li>Generar recomendaciones en base a tus preferencias</li>
        </ul>
        
        <h2>Uso de la información</h2>
        <p>No compartimos tu información personal con terceros. Tus datos se almacenan 
        de forma segura en Firebase (Google Cloud).</p>
        
        <h2>Contacto</h2>
        <p>Para consultas sobre esta política: buscafes.ai@gmail.com</p>
        
        <p><a href="/">Volver al inicio</a></p>
    </body>
    </html>
    '''

@server.route('/terminos')
def terminos():
    return '''
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <title>Términos de Servicio - Buscafes</title>
        <style>
            body { font-family: 'Montserrat', Arial, sans-serif; max-width: 800px; margin: 50px auto; padding: 20px; line-height: 1.6; }
            h1 { color: #104547; }
            a { color: #104547; }
        </style>
    </head>
    <body>
        <h1>Términos de Servicio</h1>
        <p><strong>Última actualización:</strong> Febrero 2026</p>
        
        <h2>Uso del servicio</h2>
        <p>Buscafes es una aplicación gratuita para descubrir cafeterías. Al usar nuestro servicio, 
        aceptás estos términos.</p>
        
        <h2>Cuentas de usuario</h2>
        <p>Podés iniciar sesión con Google. Sos responsable de mantener la seguridad de tu cuenta.</p>
        
        <h2>Limitación de responsabilidad</h2>
        <p>La información sobre cafeterías se proporciona "tal cual". No garantizamos la exactitud 
        de los horarios, ubicaciones o calificaciones.</p>
        
        <h2>Contacto</h2>
        <p>buscafes.ai@gmail.com</p>
        
        <p><a href="/">Volver al inicio</a></p>
    </body>
    </html>
    '''

@server.route('/perfil')
def perfil():

    # Usar las mismas variables de entorno
    firebase_config_perfil = FIREBASE_CONFIG
    
    html = '''
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <title>Mi Perfil - Buscafes</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <link rel="icon" type="image/png" href="/assets/icono_cafeterias.png">
        <!-- Firebase SDK -->
        <script type="module">
            import { initializeApp } from 'https://www.gstatic.com/firebasejs/10.8.0/firebase-app.js';
            import { getAuth, onAuthStateChanged, signOut, signInWithPopup, GoogleAuthProvider, 
                 signInWithEmailAndPassword, createUserWithEmailAndPassword } from 'https://www.gstatic.com/firebasejs/10.8.0/firebase-auth.js';
            import { getFirestore, collection, query, where, getDocs, getDoc, addDoc, 
                     updateDoc, deleteDoc, serverTimestamp, doc, setDoc, increment } 
                from 'https://www.gstatic.com/firebasejs/10.8.0/firebase-firestore.js';
                 
            const firebaseConfig = __FIREBASE_CONFIG_PERFIL__;
    
            const app = initializeApp(firebaseConfig);
            const auth = getAuth(app);
            const db = getFirestore(app);
            
            window.firebaseAuth = auth;
            window.firebaseDb = db;
            window.firebaseSignOut = () => signOut(auth);
            window.firebaseGoogleLogin = () => signInWithPopup(auth, new GoogleAuthProvider());
            window.firebaseEmailLogin = (email, pass) => signInWithEmailAndPassword(auth, email, pass); 
            window.firebaseEmailSignup = (email, pass) => createUserWithEmailAndPassword(auth, email, pass); 
            window.firebaseUtils = { collection, query, where, getDocs, getDoc, addDoc, updateDoc, deleteDoc, serverTimestamp, doc, setDoc, increment };
            
            onAuthStateChanged(auth, (user) => {
                if (user) {
                    localStorage.setItem('buscafes_user_email', user.email);
                } else {
                    localStorage.removeItem('buscafes_user_email');
                }
            
                // ← CLAVE: initPerfil se llama UNA vez, cuando Firebase ya resolvió el auth state
                if (!window._perfilInitDone) {
                    window._perfilInitDone = true;
                    // limpiarSiCambioUsuario necesita el user resuelto, no el currentUser aún vacío
                    if (typeof limpiarSiCambioUsuario === 'function') limpiarSiCambioUsuario(user);
                    if (typeof initPerfil === 'function') initPerfil();
                } else {
                    // Si el auth cambia DESPUÉS del init (e.g. login en otra pestaña), actualizar nombre
                    const txt = document.getElementById('username-text');
                    if (txt && typeof getUserName === 'function') txt.textContent = getUserName();
                }
            
                if (typeof updateAnonDisclaimer === 'function') updateAnonDisclaimer();
            });
        </script>
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body { 
                font-family: 'Montserrat', Arial, sans-serif; 
                background: #f5f5f5;
                padding-bottom: 80px;
            }
            .app-header-contact {
                display: flex;
                gap: 15px;
                align-items: center;
            }
            .app-header-contact a {
                display: flex;
                align-items: center;
                justify-content: center;
                width: 32px;
                height: 32px;
                background: rgba(218, 198, 154, 0.2);
                border-radius: 50%;
                transition: all 0.2s;
            }
            .app-header-contact a:hover {
                background: #dac69a;
            }
            .app-header-contact img {
                width: 18px;
                height: 18px;
                filter: brightness(0) invert(1);
            }            
            /* Header */
            .app-header {
                background: #104547;
                padding: 12px 20px;
                display: flex;
                justify-content: space-between;
                align-items: center;
                position: sticky;
                top: 0;
                z-index: 1000;
            }
            .app-header-logo {
                height: 40px;
                width: auto;
            }
            
            /* Stats Cards */
            .stats-container {
                display: grid;
                grid-template-columns: repeat(2, 1fr);
                gap: 12px;
                padding: 16px;
                max-width: 600px;
                margin: 0 auto;
            }
            .stat-card {
                background: white;
                border-radius: 12px;
                padding: 16px 8px;
                text-align: center;
                box-shadow: 0 2px 8px rgba(0,0,0,0.08);
            }
            .stat-number {
                font-size: 28px;
                font-weight: bold;
                color: #104547;
            }
            .stat-label {
                font-size: 11px;
                color: #666;
                margin-top: 4px;
            }
            
            /* Badges Section - COMPACTO CON NOMBRE VISIBLE */
            .badges-section {
                max-width: 600px;
                margin: 0 auto;
                padding: 0 16px 12px;
            }
            
            .section-title {
                font-size: 16px;
                font-weight: 600;
                color: #333;
                margin-bottom: 12px;
                display: flex;
                align-items: center;
                gap: 8px;
            }
            
            .badges-container {
                display: flex;
                gap: 12px;
                overflow-x: auto;
                padding-bottom: 8px;
                scrollbar-width: none;
            }
            
            .badges-container::-webkit-scrollbar {
                display: none;
            }
            
            .badge {
                display: flex;
                flex-direction: column;
                align-items: center;
                gap: 6px;
                min-width: 70px;
                flex-shrink: 0;
            }
            
            .badge-circle {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                width: 50px;
                height: 50px;
                border-radius: 50%;
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: 24px;
                box-shadow: 0 2px 8px rgba(102, 126, 234, 0.3);
                transition: box-shadow 0.2s;  /* ← QUITAR transform del transition */
                cursor: pointer;
            }
            
            .badge-circle:hover {
                box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
                /* ← QUITAR transform: scale(1.1) */
            }
            
            .badge-circle.locked {
                background: #e0e0e0;
                opacity: 0.5;
            }
            
            .badge-name {
                font-size: 9px;
                color: #666;
                text-align: center;
                font-weight: 500;
                line-height: 1.2;
                max-width: 70px;
            }
            
            .badge.locked .badge-name {
                color: #999;
            }
            
            /* Lista de cafeterías */
            .cafes-section {
                max-width: 600px;
                margin: 0 auto;
                padding: 0 16px;
            }
            .cafe-card {
                background: white;
                border-radius: 12px;
                padding: 16px;
                margin-bottom: 12px;
                box-shadow: 0 2px 8px rgba(0,0,0,0.08);
            }
            .cafe-header {
                display: flex;
                justify-content: space-between;
                align-items: start;
                margin-bottom: 12px;
            }
            .cafe-name {
                font-weight: 600;
                color: #333;
                font-size: 16px;
            }
            .cafe-neighborhood {
                font-size: 12px;
                color: #666;
                margin-top: 2px;
            }
            
            /* Contador de visitas */
            .visit-counter {
                display: flex;
                align-items: center;
                gap: 12px;
                background: #f5f5f5;
                padding: 8px 12px;
                border-radius: 20px;
            }
            .visit-btn {
                width: 28px;
                height: 28px;
                border-radius: 50%;
                border: none;
                background: #104547;
                color: white;
                font-size: 18px;
                cursor: pointer;
                display: flex;
                align-items: center;
                justify-content: center;
            }
            .visit-btn:hover {
                background: #0a2e30;
            }
            .visit-count {
                font-weight: 600;
                min-width: 20px;
                text-align: center;
            }
            
            /* Rating */
            .rating-section {
                margin: 12px 0;
                display: flex;
                align-items: center;
                gap: 8px;
            }
            .star-rating {
                display: flex;
                gap: 4px;
            }
            .star {
                font-size: 20px;
                color: #ddd;
                cursor: pointer;
                transition: color 0.2s;
            }
            .star.active {
                color: #ffc107;
            }
            .star:hover {
                color: #ffc107;
            }
            
            /* Comentario */
            .comment-section {
                margin-top: 12px;
            }
            .comment-textarea {
                width: 100%;
                padding: 10px;
                border: 1px solid #e0e0e0;
                border-radius: 8px;
                font-family: inherit;
                font-size: 13px;
                resize: vertical;
                min-height: 60px;
            }
            .comment-textarea:focus {
                outline: none;
                border-color: #104547;
            }
            .comment-actions {
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-top: 8px;
            }
            .privacy-toggle {
                display: flex;
                align-items: center;
                gap: 6px;
                font-size: 12px;
                color: #666;
                cursor: pointer;
            }
            .privacy-toggle input {
                cursor: pointer;
            }
            .save-comment-btn {
                background: #104547;
                color: white;
                border: none;
                padding: 6px 16px;
                border-radius: 6px;
                font-size: 12px;
                cursor: pointer;
            }
            
            /* Precio */
            .price-section {
                margin-top: 8px;
                display: flex;
                gap: 8px;
                align-items: center;
            }
            .price-tag {
                padding: 4px 12px;
                border-radius: 12px;
                border: 1px solid #e0e0e0;
                font-size: 12px;
                cursor: pointer;
                color: #666;
            }
            .price-tag.active {
                background: #104547;
                color: white;
                border-color: #104547;
            }
            
            /* Navbar inferior */
            .bottom-navbar-simple {
                position: fixed;
                bottom: 0;
                left: 0;
                right: 0;
                height: 60px;
                background: white;
                border-top: 1px solid #e0e0e0;
                display: flex;
                justify-content: space-around;
                align-items: center;
                z-index: 2700;
            }
            .nav-item {
                display: flex;
                flex-direction: column;
                align-items: center;
                gap: 2px;
                text-decoration: none;
                color: #666;
                font-size: 11px;
            }
            .nav-item.active {
                color: #104547;
            }
            .nav-item svg {
                width: 24px;
                height: 24px;
            }
            /* Rating con medias estrellas */
            .star-rating {
                display: inline-flex;
                gap: 2px;
                align-items: center;
            }
            .star {
                font-size: 20px;
                color: #ddd;
                cursor: pointer;
                transition: color 0.2s;
                position: relative;
            }
            .star.active {
                color: #ffc107;
            }
            .star:hover {
                color: #ffc107;
            }
            /* Media estrella */
            .star.half {
                position: relative;
            }
            .star.half::after {
                content: '★';
                position: absolute;
                left: 0;
                top: 0;
                width: 50%;
                overflow: hidden;
                color: #ffc107;
            }

            /* ===== CUSTOM UI COMPONENTS ===== */
            .bc-toast {
                position: fixed;
                bottom: 80px;
                left: 50%;
                transform: translateX(-50%);
                background: #104547;
                color: #fffff5;
                padding: 10px 20px;
                border-radius: 20px;
                font-size: 13px;
                font-weight: 600;
                z-index: 9999;
                opacity: 0;
                transition: opacity 0.3s ease;
                pointer-events: none;
                white-space: nowrap;
            }
            
            .bc-overlay {
                position: fixed;
                inset: 0;
                background: rgba(0,0,0,0.4);
                z-index: 4000;
                display: flex;
                align-items: flex-end;
                justify-content: center;
                animation: fadeIn 0.2s ease;
            }
            
            .bc-sheet {
                background: white;
                border-radius: 20px 20px 0 0;
                width: 100%;
                max-width: 500px;
                padding: 24px 20px 36px;
                animation: slideUp 0.3s ease;
            }
            
            .bc-sheet-handle {
                width: 40px;
                height: 4px;
                background: #ddd;
                border-radius: 2px;
                margin: 0 auto 20px;
            }
            
            .bc-sheet-title {
                font-size: 17px;
                font-weight: 700;
                color: #104547;
                margin-bottom: 10px;
                text-align: center;
            }
            
            .bc-sheet-body {
                font-size: 14px;
                color: #555;
                text-align: center;
                line-height: 1.5;
                margin-bottom: 20px;
            }
            
            .bc-sheet-btn {
                width: 100%;
                padding: 13px;
                background: #104547;
                color: white;
                border: none;
                border-radius: 12px;
                font-size: 15px;
                font-weight: 600;
                cursor: pointer;
                font-family: 'Montserrat', sans-serif;
            }
            
            .bc-sheet-btn-secondary {
                background: none;
                color: #104547;
                border: 1.5px solid #104547;
                margin-top: 10px;
            }
            
            .bc-sheet-input {
                width: 100%;
                padding: 12px 14px;
                border: 1.5px solid #ddd;
                border-radius: 10px;
                font-size: 15px;
                font-family: 'Montserrat', sans-serif;
                box-sizing: border-box;
                margin-bottom: 16px;
                outline: none;
            }
            
            .bc-sheet-input:focus {
                border-color: #104547;
            }
            
            .bc-badge-icon {
                font-size: 48px;
                text-align: center;
                margin-bottom: 12px;
            }
            
            @keyframes slideUp {
                from { transform: translateY(100%); }
                to { transform: translateY(0); }
            }
            
            @keyframes fadeIn {
                from { opacity: 0; }
                to { opacity: 1; }
            }

            /* Menú desplegable del perfil */
            .profile-menu {
                position: fixed;
                bottom: 70px;
                left: 50%;
                transform: translateX(-50%);
                width: 60%;
                max-width: 224px;
                background: white;
                border-radius: 16px;
                box-shadow: 0 -4px 20px rgba(0,0,0,0.15);
                z-index: 2800;
                overflow: hidden;
                animation: slideUpMenu 0.2s ease-out;
            }
            
            @keyframes slideUpMenu {
                from { opacity: 0; transform: translateX(-50%) translateY(20px); }
                to { opacity: 1; transform: translateX(-50%) translateY(0); }
            }
            
            
        </style>
    </head>
    <body>
        <div class="app-header">
            <img src="/assets/buscafes_header2.png" alt="Buscafes" class="app-header-logo">
            <div class="app-header-contact">
                <a href="mailto:buscafes.ai@gmail.com">
                    <img src="https://jsonbuscafe.blob.core.windows.net/contbuscafe/envelope-solid.svg" alt="Email">
                </a>
                <a href="https://www.instagram.com/buscafes.ai" target="_blank">
                    <img src="https://jsonbuscafe.blob.core.windows.net/contbuscafe/instagram-brands-solid.svg" alt="Instagram">
                </a>
            </div>
        </div>

        <!-- Stats -->
        <!-- Nombre de usuario -->
        <div style="max-width: 600px; margin: 16px auto 8px; padding: 0 16px; text-align: center;">
            <div id="user-display-name" style="font-size: 18px; font-weight: 600; color: #104547; cursor: pointer; display: inline-flex; align-items: center; gap: 6px;" onclick="editarNombre()">
                <span id="username-text">Cargando...</span>
                <span style="font-size: 12px; color: #999;">✏️</span>
            </div>
        </div>

        <div id="anon-disclaimer" style="display:none;max-width:600px;max-width:600px;margin:0 auto 12px;padding:0 16px;">
            <div style="background:#fff8e1;border:1px solid #ffe082;border-radius:10px;padding:10px 14px;display:flex;align-items:center;gap:10px;">
                <span style="font-size:18px;flex-shrink:0;">⚠️</span>
                    <div style="font-size:11px;color:#856404;margin-top:2px;">
                        Estás en modo anónimo. Te recomiendo logearte para no perder los datos almacenados.
                    </div>
            </div>
        </div>
        
        <div class="stats-container" style="grid-template-columns: repeat(3, 1fr);">
            <div class="stat-card">
                <div class="stat-number" id="stat-visitadas">0</div>
                <div class="stat-label">Visitadas</div>
            </div>
            <div class="stat-card">
                <div class="stat-number" id="stat-favoritas">0</div>
                <div class="stat-label">Favoritas</div>
            </div>
            <div class="stat-card">
                <div class="stat-number" id="stat-badges">0</div>
                <div class="stat-label">Medallas</div>
            </div>
        </div>

        <!-- Badges -->
        <div class="badges-section">
            <div class="section-title">🏆 Tus insignias</div>
            <div class="badges-container" id="badges-container">
                <!-- Se llena con JS -->
            </div>
        </div>
        
        <!-- Lista de cafeterías -->
        <div class="cafes-section">
            <div class="section-title">☕ Tus cafeterías visitadas</div>
            <div class="profile-search-wrapper" style="padding: 0 16px 12px 16px;">
                <input type="text" 
                       id="profile-search" 
                       placeholder="🔍 Buscar en mis cafeterías..." 
                       style="width: 100%; padding: 10px 14px; border: 1px solid #e0e0e0; border-radius: 20px; font-size: 13px; font-family: 'Montserrat', sans-serif; box-sizing: border-box;">
            </div>
            <div id="cafes-list">
                <!-- Se llena con JS -->
            </div>
        </div>
        
        <!-- Navbar -->
        <div class="bottom-navbar-simple">
            <a href="/perfil" class="nav-item active">
                <img src="/assets/icon_usuario.png" style="width:24px;height:24px;">
                <span>Perfil</span>
            </a>
            <a href="/" class="nav-item">
                <img src="/assets/icono_mapa.png" style="width:24px;height:24px;">
                <span>Mapa</span>
            </a>
            <a href="/comunidad" class="nav-item">
                <img src="/assets/icono_comunidad2.png" style="width:24px;height:24px;">
                <span>Comunidad</span>
            </a>
        </div>

        <script>
            // ============ FUNCIONES HELPER (SINCRONIZACIÓN CON MAPA) ============
            function getCafeData(id) {
                const data = JSON.parse(localStorage.getItem('buscafes_user_data') || '{}');
                return data[id] || {
                    isFavorite: false,
                    isVisited: false,
                    visitCount: 0,
                    rating: 0,
                    comment: '',
                    isCommentPublic: false,
                    priceRange: '',
                    lastVisit: null
                };
            }
            
            function saveCafeData(id, newData) {
                const data = JSON.parse(localStorage.getItem('buscafes_user_data') || '{}');
                if (!data[id]) data[id] = {};
                Object.assign(data[id], newData);
                localStorage.setItem('buscafes_user_data', JSON.stringify(data));
            }


            function getOrCreateAnonId() {
                let id = localStorage.getItem('buscafes_anon_id');
                if (!id) {
                    id = 'anon_' + Math.random().toString(36).substring(2, 15)
                                 + Math.random().toString(36).substring(2, 15);
                    localStorage.setItem('buscafes_anon_id', id);
                }
                return id;
            }
            
            function getActiveUid() {
                if (window.firebaseAuth?.currentUser) return window.firebaseAuth.currentUser.uid;
                return getOrCreateAnonId();
            }
            
            function getActiveUsername() {
                return localStorage.getItem('buscafes_username') || getOrCreateAnonId();
            }
            
            async function syncComentarioFirestore(id, nombre, texto, isPublic) {
                if (!window.firebaseAuth?.currentUser) return;
                if (!window.firebaseDb) return;
                const { collection, query, where, getDocs, addDoc, updateDoc, deleteDoc, serverTimestamp } = window.firebaseUtils;
                const uid = getActiveUid();
            
                const q = query(
                    collection(window.firebaseDb, 'comentarios'),
                    where('uid', '==', uid),
                    where('cafeId', '==', id)
                );
            
                try {
                    const snap = await getDocs(q);
                    if (isPublic && texto?.trim()) {
                        if (snap.empty) {
                            await addDoc(collection(window.firebaseDb, 'comentarios'), {
                                uid,
                                username: getActiveUsername(),
                                cafeId: id,
                                cafe: nombre,
                                texto: texto.trim(),
                                fecha: serverTimestamp()
                            });
                        } else {
                            await updateDoc(snap.docs[0].ref, {
                                texto: texto.trim(),
                                username: getActiveUsername()
                            });
                        }
                    } else {
                        snap.forEach(async (d) => await deleteDoc(d.ref));
                    }
                } catch (err) {
                    console.warn('Firestore comentario error:', err);
                }
            }       


            async function syncUsernameFirestore(nuevoNombre) {
                localStorage.setItem('buscafes_username', nuevoNombre);
                if (!window.firebaseDb || !window.firebaseAuth?.currentUser) return;
                const { collection, query, where, getDocs, updateDoc, doc, setDoc } = window.firebaseUtils;
                const uid = getActiveUid();
            
                try {
                    await setDoc(doc(window.firebaseDb, 'users', uid),
                        { username: nuevoNombre },
                        { merge: true }
                    );
            
                    const q = query(
                        collection(window.firebaseDb, 'comentarios'),
                        where('uid', '==', uid)
                    );
                    const snap = await getDocs(q);
                    snap.forEach(async (d) => {
                        await updateDoc(d.ref, { username: nuevoNombre });
                    });
                } catch (err) {
                    console.warn('Firestore username sync error:', err);
                }
            }
            
            // ============ DATOS ============
            const geoLookup = __GEO_LOOKUP__;
        
            // ============ FILTRO ANTI-TROLLING ============
            function sanitizeUsername(name) {
                if (!name || typeof name !== 'string') return null;
                
                // Trim y eliminar espacios múltiples
                name = name.trim().replace(/\s+/g, ' ');
                
                // Máximo 20 caracteres
                if (name.length > 20) name = name.substring(0, 20);
                
                // Solo letras, números, espacios, guiones, guiones bajos
                name = name.replace(/[^a-zA-ZáéíóúÁÉÍÓÚñÑ0-9\s\-_]/g, '');
                
                // No puede ser solo números o espacios
                if (/^[\d\s\-_]+$/.test(name)) return null;
                
                // Filtro básico de palabras ofensivas (agregá más si querés)
                const palabrasBloqueadas = ['puto', 'puta', 'mierda', 'hijo de puta', 'concha', 'verga', 'pija'];
                const nameLower = name.toLowerCase();
                if (palabrasBloqueadas.some(palabra => nameLower.includes(palabra))) {
                    return null;
                }
                
                return name;
            }
        
            // ============ NOMBRE DE USUARIO ============
            const nombresAnonimos = ['BaristaAnónimo', 'CortadoLover', 'Lágrima', 'Espresso', 'Ristretto', 'Macchiato', 'Affogato', 'Mocha', 'Capuchino', 'FlatWhite'];
            const numeroRandom = Math.floor(Math.random() * 900) + 100;

            function editarNombre() {
                const currentName = localStorage.getItem('buscafes_username') || '';
                showPrompt('¿Cómo querés llamarte?', currentName, async function(newName) {
                    const sanitized = sanitizeUsername(newName);
                    if (!sanitized) {
                        showToast('❌ Nombre inválido');
                        return;
                    }
                    await syncUsernameFirestore(sanitized);
                    if (usernameText) usernameText.textContent = sanitized;
                    showToast('✓ Nombre actualizado');
                });
            }
            
            function getUserName() {
                // PRIORIDAD 1: username guardado explícitamente
                const savedName = localStorage.getItem('buscafes_username');
                if (savedName) return savedName;
                
                // PRIORIDAD 2: Firebase currentUser (fallback)
                if (window.firebaseAuth && window.firebaseAuth.currentUser) {
                    const email = window.firebaseAuth.currentUser.email;
                    if (email) {
                        const username = email.split('@')[0];
                        localStorage.setItem('buscafes_username', username);
                        return username;
                    }
                }
                
                // PRIORIDAD 3: email guardado en localStorage (fallback)
                const savedEmail = localStorage.getItem('buscafes_user_email');
                if (savedEmail) {
                    const username = savedEmail.split('@')[0];
                    localStorage.setItem('buscafes_username', username);
                    return username;
                }
                
                // PRIORIDAD 4: generar nuevo (solo si no existe nada)
                const nombresAnonimos = ['BaristaAnónimo', 'CortadoAnónimo', 'LágrimaAnónima', 'EspressoAnónimo', 'RistrettoAnónimo', 'MacchiatoAnónimo', 'AffogatoAnónimo', 'MochaAnónimo', 'CapuchinoAnónimo', 'FlatWhiteAnónimo'];
                const numeroRandom = Math.floor(Math.random() * 900) + 100;
                const randomNombre = nombresAnonimos[Math.floor(Math.random() * nombresAnonimos.length)];
                const nombreGenerado = randomNombre + numeroRandom;
                localStorage.setItem('buscafes_username', nombreGenerado);
                return nombreGenerado;
            }
                        

            // ============ NOMBRE DE USUARIO - ARRIBA DE STATS ============
            const usernameText = document.getElementById('username-text');
            const badgesContainer = document.getElementById('badges-container');  // ← agregar
            
            // Mostrar/ocultar disclaimer según si está logueado
            function updateAnonDisclaimer() {
                const disclaimer = document.getElementById('anon-disclaimer');
                if (!disclaimer) return;
                const isLoggedIn = window.firebaseAuth?.currentUser || 
                                   localStorage.getItem('buscafes_user_email');
                disclaimer.style.display = isLoggedIn ? 'none' : 'block';
            }
            
            window.irALoginPerfil = async function() {
                try {
                    const result = await window.firebaseGoogleLogin();
                    const email = result.user.email;
                    localStorage.setItem('buscafes_user_email', email);
                    localStorage.setItem('buscafes_username', email.split('@')[0]);
                    if (usernameText) usernameText.textContent = email.split('@')[0];  // ← usar la de arriba, no redeclararla
                    updateAnonDisclaimer();
                } catch (error) {
                    showToast('❌ Error al iniciar sesión');
                }
            };


            // ============ BADGES ============
            
            const allBadges = [
                // Visitas generales
                {icon: '🐣', name: 'El Principiante',   desc: 'Visitá 1 cafetería',        requirement: 1,    type: 'visit',    gradient: 'linear-gradient(135deg, #a8edea, #fed6e3)'},
                {icon: '⚽', name: 'El Diego',           desc: 'Visitá 10 cafeterías',      requirement: 10,   type: 'visit',    gradient: 'linear-gradient(135deg, #667eea, #764ba2)'},
                {icon: '🎯', name: 'El Experimentado',   desc: 'Visitá 100 cafeterías',     requirement: 100,  type: 'visit',    gradient: 'linear-gradient(135deg, #4facfe, #00f2fe)'},
                {icon: '🔥', name: 'El Demente',         desc: 'Visitá 1000 cafeterías',    requirement: 1000, type: 'visit',    gradient: 'linear-gradient(135deg, #fa709a, #fee140)'},
                {icon: '👽', name: 'Inchequeable',       desc: 'Visitá +2000 cafeterías',   requirement: 2000, type: 'visit',    gradient: 'linear-gradient(135deg, #0f0c29, #302b63)'},
            
                // Barrios
                {icon: '🌿', name: 'Palermitano',        desc: 'Visitá 10 cafeterías de Palermo',                    requirement: 10, type: 'palermo',  gradient: 'linear-gradient(135deg, #56ab2f, #a8e063)'},
                {icon: '🏘️', name: 'Capo Barrial',       desc: 'Visitá 10 cafeterías de un mismo barrio',            requirement: 10, type: 'barrio',   gradient: 'linear-gradient(135deg, #f6d365, #fda085)'},
            
                // Favoritos
                {icon: '❤️',  name: 'Primer Amor',       desc: 'Agregá tu primera cafetería a favoritos',            requirement: 1,  type: 'favorite', gradient: 'linear-gradient(135deg, #f093fb, #f5576c)'},
                {icon: '💘', name: 'Poligámicoffee',     desc: 'Tenés 10 cafeterías en favoritos',                   requirement: 10, type: 'favorite', gradient: 'linear-gradient(135deg, #c471f5, #fa71cd)'},
            
                // Notas
                {icon: '📝', name: 'El Notero',          desc: 'Dejá 5 notas en cafeterías',                         requirement: 5,  type: 'nota',     gradient: 'linear-gradient(135deg, #ffd89b, #19547b)'},
                {icon: '🤝', name: 'El Solidario',       desc: 'Dejá +20 notas públicas en cafeterías',              requirement: 20, type: 'notapub',  gradient: 'linear-gradient(135deg, #11998e, #38ef7d)'},
            ];        
                       
            // ============ FUNCIONES DE ACTUALIZACIÓN ============
            function updateVisit(id, delta) {
                const data = getCafeData(id);
                const nombre = data.nombre || id;
                const currentCount = data.visitCount || 1;
                const newCount = currentCount + delta;
            
                if (delta < 0 && currentCount === 1) {
                    showSheet({
                        title: '¿Eliminar cafetería?',
                        body: `"${nombre}" se quitará de tu lista.`,
                        btnText: 'Eliminar',
                        showCancel: true,
                        onConfirm: () => {
                            const allData = JSON.parse(localStorage.getItem('buscafes_user_data') || '{}');
                            delete allData[id];
                            localStorage.setItem('buscafes_user_data', JSON.stringify(allData));
            
                            if (window.firebaseDb && window.firebaseAuth?.currentUser) {
                                const { doc, deleteDoc, getDoc, setDoc, increment } = window.firebaseUtils;
                                const uid = getActiveUid();
            
                                deleteDoc(doc(window.firebaseDb, 'users', uid, 'cafes', id))
                                    .catch(err => console.warn('Firestore delete error:', err));
            
                                const userRef = doc(window.firebaseDb, 'users', uid);
                                getDoc(userRef).then(snap => {
                                    const currentCount = snap.data()?.visitCount || 0;
                                    if (currentCount > 0) {
                                        setDoc(userRef, {
                                            visitCount: increment(-1)
                                        }, { merge: true }).catch(err => console.warn('Firestore visitCount error:', err));
                                    }
                                });
                            }
            
                            renderCafes(document.getElementById('profile-search').value);
                        }
                    });
                    return;
                }
            
                const newData = {
                    visitCount: Math.max(1, newCount),
                    lastVisit: new Date().toISOString()
                };
                saveCafeData(id, newData);
            
                if (window.firebaseDb && window.firebaseAuth?.currentUser) {
                    const { doc, setDoc } = window.firebaseUtils;
                    const uid = getActiveUid();
                    setDoc(doc(window.firebaseDb, 'users', uid, 'cafes', id),
                        newData,
                        { merge: true }
                    ).catch(err => console.warn('Firestore visitCount error:', err));
                }
            
                renderCafes(document.getElementById('profile-search').value);
            }
            
            function toggleFavorito(id) {
                const data = getCafeData(id);
                const newFav = !data.isFavorite;
                const yaVisitado = data.isVisited;
                const newData = {
                    isFavorite: newFav,
                    isVisited: true
                };
                saveCafeData(id, newData);
            
                if (!window.firebaseDb || !window.firebaseAuth?.currentUser) {
                    renderCafes(document.getElementById('profile-search').value);
                    return;  // ← anónimos terminan acá
                }
            
                // Solo logueados llegan hasta acá
                const { doc, setDoc, getDoc, increment } = window.firebaseUtils;
                const uid = getActiveUid();
            
                setDoc(doc(window.firebaseDb, 'cafes', id),
                    { favCount: increment(newFav ? 1 : -1), nombre: data.nombre },
                    { merge: true }
                ).catch(err => console.warn('Firestore fav error:', err));
            
                if (!yaVisitado) {
                    if (newFav) {
                        setDoc(doc(window.firebaseDb, 'users', uid), {
                            username: getActiveUsername(),
                            visitCount: increment(1)
                        }, { merge: true }).catch(err => console.warn('Firestore visitCount error:', err));
                    } else {
                        const userRef = doc(window.firebaseDb, 'users', uid);
                        getDoc(userRef).then(snap => {
                            const currentCount = snap.data()?.visitCount || 0;
                            if (currentCount > 0) {
                                setDoc(userRef, {
                                    username: getActiveUsername(),
                                    visitCount: increment(-1)
                                }, { merge: true }).catch(err => console.warn('Firestore visitCount error:', err));
                            }
                        });
                    }
                }
            
                setDoc(doc(window.firebaseDb, 'users', uid, 'cafes', id),
                    newData,
                    { merge: true }
                ).catch(err => console.warn('Firestore user cafe error:', err));
            
                renderCafes(document.getElementById('profile-search').value);
            }
            
            function setRating(id, rating) {
                const oldData = getCafeData(id);
                const oldRating = oldData.rating || 0;
                saveCafeData(id, { rating: rating });
            
                const details = document.getElementById('details-' + id);
                if (details) {
                    const starContainer = details.querySelector('.star-rating');
                    if (starContainer) starContainer.innerHTML = renderStarRating(id, rating);
                    const ratingText = details.querySelector('.star-rating + span');
                    if (ratingText) ratingText.textContent = rating + '/5';
                }
            
                if (!window.firebaseDb || !window.firebaseAuth?.currentUser) return;
                const { doc, setDoc, increment } = window.firebaseUtils;
                const uid = getActiveUid();
                const isNew = oldRating === 0;
                const delta = rating - oldRating;
            
                setDoc(doc(window.firebaseDb, 'cafes', id), {
                    ratingSum: increment(delta),
                    ratingCount: increment(isNew ? 1 : 0)
                }, { merge: true }).catch(err => console.warn('Firestore rating error:', err));
            
                setDoc(doc(window.firebaseDb, 'users', uid, 'cafes', id),
                    { rating: rating },
                    { merge: true }
                ).catch(err => console.warn('Firestore rating user error:', err));
            }
            
            function saveComment(id, comment) {
                const data = getCafeData(id);
                saveCafeData(id, { comment: comment });
                showToast('✓ Nota guardada');
                syncComentarioFirestore(id, data.nombre, comment, data.isCommentPublic);
            
                if (window.firebaseDb && window.firebaseAuth?.currentUser) {
                    const { doc, setDoc } = window.firebaseUtils;
                    const uid = getActiveUid();
                    setDoc(doc(window.firebaseDb, 'users', uid, 'cafes', id),
                        { comment: comment },
                        { merge: true }
                    ).catch(err => console.warn('Firestore note error:', err));
                }
            }
            
            function togglePublic(id, isPublic) {
                if (!window.firebaseAuth?.currentUser) return;
                const data = getCafeData(id);
                saveCafeData(id, { isCommentPublic: isPublic });
                syncComentarioFirestore(id, data.nombre, data.comment, isPublic);
            }
            
            function toggleExpand(id) {
                const details = document.getElementById('details-' + id);
                if (details) {
                    const isVisible = details.style.display !== 'none';
                    details.style.display = isVisible ? 'none' : 'block';
                }
            }
            
            function renderStarRating(id, rating) {
                let html = '';
                const uniqueId = 'stars-' + id;
            
                for (let i = 1; i <= 5; i++) {
                    const isFull = rating >= i;
                    const isHalf = rating >= (i - 0.5) && rating < i;
            
                    let starClass = 'star';
                    if (isFull) starClass += ' active';
            
                    html += `<span class="${starClass}" data-star="${i}" data-stars-id="${uniqueId}" style="font-size:24px;color:${isFull || isHalf ? '#ffc107' : '#ddd'};cursor:pointer;user-select:none;display:inline-block;position:relative;">`;
            
                    if (isHalf && !isFull) {
                        html += `<span style="position:absolute;top:0;left:0;width:50%;overflow:hidden;color:#ffc107;">★</span>`;
                        html += `<span style="color:#ddd;">★</span>`;
                    } else {
                        html += `★`;
                    }
            
                    html += `</span>`;
                }
            
                setTimeout(() => {
                    document.querySelectorAll(`[data-stars-id="${uniqueId}"]`).forEach(star => {
                        star.onclick = function(e) {
                            const starNum = parseInt(this.dataset.star);
                            const rect = this.getBoundingClientRect();
                            const clickX = e.clientX - rect.left;
                            const halfWidth = rect.width / 2;
                            const newRating = clickX < halfWidth ? starNum - 0.5 : starNum;
                            setRating(id, newRating);
                        };
                    });
                }, 0);
            
                return html;
            }

            // Verificar que los datos locales corresponden al usuario logueado
            function limpiarSiCambioUsuario(user) {
                const prevEmail = localStorage.getItem('buscafes_user_email');
                if (prevEmail && user && prevEmail !== user.email) {
                    localStorage.removeItem('buscafes_user_data');
                    localStorage.removeItem('buscafes_username');
                    window.userCafeData = {};
                }
            }


            // ============ INICIALIZACIÓN ============
            function initPerfil() {
                const userData = JSON.parse(localStorage.getItem('buscafes_user_data') || '{}');
            
                // username
                if (usernameText) usernameText.textContent = getUserName();
                updateAnonDisclaimer();
            
                // stats
                const visitadas = Object.values(userData).filter(c => c.isVisited).length;
                const favoritas = Object.values(userData).filter(c => c.isFavorite).length;
                document.getElementById('stat-visitadas').textContent = visitadas;
                document.getElementById('stat-favoritas').textContent = favoritas;
            
                // badges
                const notasCount = Object.values(userData).filter(d => d.comment && d.comment.trim()).length;
                const notasPublicas = Object.values(userData).filter(d => d.comment && d.comment.trim() && d.isCommentPublic).length;
                const barriosVisitados = {};
                Object.entries(userData).forEach(([id, data]) => {
                    if (data.isVisited && geoLookup[id] && geoLookup[id].barrio) {
                        const barrio = geoLookup[id].barrio;
                        barriosVisitados[barrio] = (barriosVisitados[barrio] || 0) + 1;
                    }
                });
                const maxBarrio = Math.max(0, ...Object.values(barriosVisitados));
                const barrioPalermo = barriosVisitados['Palermo'] || 0;
            
                allBadges.forEach(badge => {
                    switch(badge.type) {
                        case 'visit':    badge.unlocked = visitadas >= badge.requirement; break;
                        case 'favorite': badge.unlocked = favoritas >= badge.requirement; break;
                        case 'palermo':  badge.unlocked = barrioPalermo >= badge.requirement; break;
                        case 'barrio':   badge.unlocked = maxBarrio >= badge.requirement; break;
                        case 'nota':     badge.unlocked = notasCount >= badge.requirement; break;
                        case 'notapub':  badge.unlocked = notasPublicas >= badge.requirement; break;
                    }
                });
            
                const badgesUnlocked = allBadges.filter(b => b.unlocked).length;
                document.getElementById('stat-badges').textContent = badgesUnlocked;
            
                badgesContainer.innerHTML = '';
                allBadges.forEach(badge => {
                    const badgeEl = document.createElement('div');
                    badgeEl.className = 'badge' + (badge.unlocked ? '' : ' locked');
                    badgeEl.innerHTML = `
                        <div class="badge-circle ${badge.unlocked ? '' : 'locked'}" style="background: ${badge.unlocked ? badge.gradient : '#e0e0e0'}">
                            ${badge.unlocked ? badge.icon : '🔒'}
                        </div>
                        <div class="badge-name">${badge.name}</div>
                    `;
                    const circle = badgeEl.querySelector('.badge-circle');
                    circle.onclick = function() {
                        showSheet({ 
                            icon: badge.unlocked ? badge.icon : '🔒', 
                            title: badge.name, 
                            body: badge.unlocked ? '✅ ¡Medalla desbloqueada!<br><br>' + badge.desc : badge.desc 
                        });
                    };
                    badgesContainer.appendChild(badgeEl);
                });
            
                renderCafes();
            }
            
            // Esperar a Firebase antes de renderizar
            window.addEventListener('load', function() {
                // Fallback: si Firebase tarda más de 4s (timeout, red lenta, bloqueador de ads)
                setTimeout(function() {
                    if (!window._perfilInitDone) {
                        window._perfilInitDone = true;
                        initPerfil();
                    }
                }, 4000);
            });

         
            function renderCafes(filterText) {
                const filter = (filterText || '').toLowerCase().trim();
                const userData = JSON.parse(localStorage.getItem('buscafes_user_data') || '{}');
                const cafesFiltrados = Object.entries(userData)
                    .filter(([id, data]) => {
                        const match = data.isVisited || data.isFavorite;
                        const nombre = data.nombre || '';
                        if (!filter) return match;
                        return match && nombre.toLowerCase().includes(filter);
                    })
                    .sort((a, b) => {
                        const dateA = a[1].lastVisit || '';
                        const dateB = b[1].lastVisit || '';
                        return dateB > dateA ? 1 : -1;
                    });
            
                const cafesList = document.getElementById('cafes-list');
            
                if (cafesFiltrados.length === 0) {
                    cafesList.innerHTML = '<p style="text-align:center;color:#999;padding:20px;">No se encontraron cafeterías</p>';
                    return;
                }
            
                cafesList.innerHTML = '';
                cafesFiltrados.forEach(([id, data]) => {
                    const nombre = data.nombre || id;
                    const info = geoLookup[id] || {};
                    const hasDetails = data.comment || data.rating;
                    const safeId = id;
                    const safeNombre = nombre.replace(/'/g, "\\'");
            
                    let sitioWebHtml = '';
                    if (info.web && info.web !== 'Sin datos' && info.web !== '') {
                        const webUrl = info.web.trim().replace(/"/g, '&quot;');
                        sitioWebHtml = `<div style="font-size:11px;color:#104547;margin-top:2px;">
                            <a href="${webUrl}" target="_blank" style="color:#104547;text-decoration:none;" onclick="event.stopPropagation();">
                                🌐 ${webUrl.replace(/^https?:\/\//, '').replace(/\/$/, '')}
                            </a>
                        </div>`;
                    }
            
                    let ubicacionHtml = '';
                    if (info.dir) ubicacionHtml += `📍 ${info.dir}`;
                    if (info.barrio) ubicacionHtml += (info.dir ? ' · ' : '') + `🏘️ ${info.barrio}`;
            
                    const card = document.createElement('div');
                    card.className = 'cafe-card';
                    card.innerHTML = `
                        <div class="cafe-header-compact" style="display:flex;justify-content:space-between;align-items:center;cursor:pointer;padding:4px 0;" onclick="toggleExpand('${safeId}')">
                            <div style="flex:1;min-width:0;">
                                <div class="cafe-name" style="font-size:15px;font-weight:600;color:#104547;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${nombre}</div>
                                ${ubicacionHtml ? `<div style="font-size:11px;color:#666;margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${ubicacionHtml}</div>` : ''}
                                ${sitioWebHtml}
                            </div>
                            <div style="display:flex;align-items:center;gap:8px;flex-shrink:0;margin-left:8px;">
                                <button onclick="event.stopPropagation(); toggleFavorito('${safeId}')"
                                        style="background:none;border:none;font-size:20px;cursor:pointer;padding:4px;line-height:1;">
                                    ${data.isFavorite ? '❤️' : '🤍'}
                                </button>
                                <div style="text-align:center;">
                                    <div style="font-size:9px;color:#999;margin-bottom:2px;">Visitas</div>
                                    <div class="visit-counter" onclick="event.stopPropagation();" style="display:flex;align-items:center;gap:8px;background:#f5f5f5;padding:6px 10px;border-radius:20px;">
                                        <button class="visit-btn" onclick="updateVisit('${safeId}', -1)" title="Restar una visita" style="width:24px;height:24px;border-radius:50%;border:none;background:#104547;color:white;font-size:16px;cursor:pointer;display:flex;align-items:center;justify-content:center;">−</button>
                                        <span class="visit-count" style="font-weight:600;min-width:16px;text-align:center;font-size:14px;">${data.visitCount || 1}</span>
                                        <button class="visit-btn" onclick="updateVisit('${safeId}', 1)" title="Sumar una visita" style="width:24px;height:24px;border-radius:50%;border:none;background:#104547;color:white;font-size:16px;cursor:pointer;display:flex;align-items:center;justify-content:center;">+</button>
                                    </div>
                                </div>
                            </div>
                            <span style="margin-left:10px;color:#104547;font-size:12px;font-weight:600;flex-shrink:0;">${hasDetails ? '📝 ' : ''}▼</span>
                        </div>
                        <div class="cafe-details" id="details-${safeId}" style="display:none;margin-top:12px;padding-top:12px;border-top:1px solid #eee;">
                            <div class="rating-section" style="margin-bottom:12px;">
                                <span style="font-size:12px;color:#666;">Tu rating:</span>
                                <div class="star-rating" style="display:inline-flex;gap:2px;margin-left:8px;">
                                    ${renderStarRating(id, data.rating)}
                                </div>
                                <span style="font-size:12px;color:#666;margin-left:8px;">${data.rating || '-'}/5</span>
                            </div>
                            <div class="comment-section">
                                <textarea class="comment-textarea" placeholder="¿Qué pediste? ¿Cómo fue la atención? Escribí tu nota..." onblur="saveComment('${safeId}', this.value)" style="width:100%;padding:10px;border:1px solid #e0e0e0;border-radius:8px;font-family:inherit;font-size:13px;resize:vertical;min-height:60px;box-sizing:border-box;">${data.comment || ''}</textarea>
                                <div class="comment-actions" style="display:flex;justify-content:space-between;align-items:center;margin-top:8px;">
                                    <label class="privacy-toggle" style="display:flex;align-items:center;gap:6px;font-size:12px;color:#666;cursor:pointer;">
                                        <input type="checkbox" ${data.isCommentPublic ? 'checked' : ''} onchange="togglePublic('${safeId}', this.checked)">
                                        <span>Hacer público</span>
                                    </label>
                                    <button class="save-comment-btn" onclick="saveComment('${safeId}', this.parentElement.previousElementSibling.value)" style="background:#104547;color:white;border:none;padding:6px 16px;border-radius:6px;font-size:12px;cursor:pointer;">Guardar</button>
                                </div>
                            </div>
                        </div>
                    `;
                    cafesList.appendChild(card);
                });
            }
            
            // ============ INICIALIZACIÓN ============
            document.getElementById('profile-search').addEventListener('input', function(e) {
                renderCafes(e.target.value);
            });


            // ===== CUSTOM UI =====
            function showToast(msg, duration = 2500) {
                let toast = document.getElementById('bc-toast');
                if (!toast) {
                    toast = document.createElement('div');
                    toast.id = 'bc-toast';
                    toast.className = 'bc-toast';
                    document.body.appendChild(toast);
                }
                toast.textContent = msg;
                clearTimeout(window._bcToastTimeout);
                toast.style.opacity = '1';
                window._bcToastTimeout = setTimeout(() => { toast.style.opacity = '0'; }, duration);
            }
            
            function showSheet({ icon = '', title, body, btnText = 'Entendido', onConfirm = null, showCancel = false, cancelText = 'Cancelar' }) {
                const overlay = document.createElement('div');
                overlay.className = 'bc-overlay';
                overlay.innerHTML = `
                    <div class="bc-sheet">
                        <div class="bc-sheet-handle"></div>
                        ${icon ? `<div class="bc-badge-icon">${icon}</div>` : ''}
                        <div class="bc-sheet-title">${title}</div>
                        <div class="bc-sheet-body">${body}</div>
                        <button class="bc-sheet-btn" id="bc-btn-confirm">${btnText}</button>
                        ${showCancel ? `<button class="bc-sheet-btn bc-sheet-btn-secondary" id="bc-btn-cancel">${cancelText}</button>` : ''}
                    </div>
                `;
                document.body.appendChild(overlay);
            
                const close = () => overlay.remove();
            
                overlay.getElementById?.('bc-btn-confirm') || overlay.querySelector('#bc-btn-confirm');
                overlay.querySelector('#bc-btn-confirm').onclick = () => {
                    close();
                    if (onConfirm) onConfirm();
                };
                if (showCancel) {
                    overlay.querySelector('#bc-btn-cancel').onclick = close;
                }
                overlay.addEventListener('click', (e) => { if (e.target === overlay) close(); });
            }
            
            function showPrompt(title, defaultValue, onConfirm) {
                const overlay = document.createElement('div');
                overlay.className = 'bc-overlay';
                overlay.innerHTML = `
                    <div class="bc-sheet">
                        <div class="bc-sheet-handle"></div>
                        <div class="bc-sheet-title">${title}</div>
                        <input class="bc-sheet-input" id="bc-prompt-input" type="text" value="${defaultValue || ''}" maxlength="20">
                        <button class="bc-sheet-btn" id="bc-btn-confirm">Guardar</button>
                        <button class="bc-sheet-btn bc-sheet-btn-secondary" id="bc-btn-cancel">Cancelar</button>
                    </div>
                `;
                document.body.appendChild(overlay);
            
                const input = overlay.querySelector('#bc-prompt-input');
                setTimeout(() => input.focus(), 100);
            
                const close = () => overlay.remove();
                overlay.querySelector('#bc-btn-confirm').onclick = () => {
                    close();
                    onConfirm(input.value);
                };
                overlay.querySelector('#bc-btn-cancel').onclick = close;
                overlay.addEventListener('click', (e) => { if (e.target === overlay) close(); });
            }

            


            
        </script>

        <!-- Menú desplegable del botón Perfil -->
        <div id="profile-menu" class="profile-menu" style="display: none;">
            <div class="profile-menu-content">
                <div class="profile-menu-header">
                    <span id="menu-username">Usuario</span>
                    <button onclick="closeProfileMenu()" class="profile-menu-close">✕</button>
                </div>
                <div class="profile-menu-items">
                    <button class="profile-menu-item" onclick="window.location.href='/'">
                        <span>🗺️</span> Volver al mapa
                    </button> 
                </div>
            </div>
        </div>
        
    </body>
    </html>
    '''
    return (html
    .replace("__GEO_LOOKUP__", json.dumps(geo_lookup, ensure_ascii=False))
    .replace("__FIREBASE_CONFIG_PERFIL__", json.dumps(firebase_config_perfil))
    )

@server.route('/comunidad')
def comunidad():
    firebase_config_comunidad = FIREBASE_CONFIG
    
    html = '''
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <title>Comunidad - Buscafes</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <link rel="icon" type="image/png" href="/assets/icono_cafeterias.png">
        <link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@400;500;600;700;800&display=swap" rel="stylesheet">
        
        <script type="module">
            import { initializeApp } from 'https://www.gstatic.com/firebasejs/10.8.0/firebase-app.js';
            import { getFirestore, collection, query, orderBy, limit, getDocs } 
                from 'https://www.gstatic.com/firebasejs/10.8.0/firebase-firestore.js';
        
            const firebaseConfig = __FIREBASE_CONFIG_COMUNIDAD__;
        
            const app = initializeApp(firebaseConfig);
            const db = getFirestore(app);
            window.firebaseDb = db;
            window.firebaseUtils = { collection, query, orderBy, limit, getDocs };
        
            window.cargarComunidad = async function() {
                console.log('cargarComunidad ejecutándose, firebaseDb:', !!window.firebaseDb);
                const { collection, query, orderBy, limit, getDocs } = window.firebaseUtils;
        
                try {
                    // ── Comentarios recientes ──
                    const qComentarios = query(
                        collection(db, 'comentarios'),
                        orderBy('fecha', 'desc'),
                        limit(20)
                    );
                    const snapComentarios = await getDocs(qComentarios);
                    window._comunidadComentarios = snapComentarios.docs.map(d => {
                        const data = d.data();
                        return {
                            user: data.username || 'Anónimo',
                            cafe: data.cafe,
                            texto: data.texto,
                            tiempo: formatTiempo(data.fecha?.toDate())
                        };
                    });
        
                    // ── Top cafés por favCount ──
                    const qCafes = query(
                        collection(db, 'cafes'),
                        orderBy('favCount', 'desc'),
                        limit(20)
                    );
                    const snapCafes = await getDocs(qCafes);
                    window._comunidadTopCafes = snapCafes.docs.map(d => ({
                        nombre: d.data().nombre || d.id,  // ← usar nombre del doc, no el id
                        favs: d.data().favCount || 0,
                        dir: window.geoLookup?.[d.id]?.dir || ''  // ← geoLookup ya indexa por id, ok
                    })).filter(c => c.favs > 0);
        
                    // ── Exploradores por visitCount ──
                    const qUsers = query(
                        collection(db, 'users'),
                        orderBy('visitCount', 'desc'),
                        limit(20)
                    );
                    const snapUsers = await getDocs(qUsers);
               
                    window._comunidadExploradores = snapUsers.docs.map((d, i) => ({
                        user: d.data().username || 'Anónimo',
                        visitas: d.data().visitCount || 0,
                        uid: d.id,
                        pos: i + 1
                    })).filter(e => e.visitas > 0);
        
                    // Re-renderizar con datos reales
                    renderPreviews();
                    renderBodies();
        
                } catch (err) {
                    console.warn('Error cargando comunidad:', err);
                }
            };
        
            function formatTiempo(date) {
                if (!date) return '';
                const diff = (Date.now() - date.getTime()) / 1000;
                if (diff < 3600) return 'hace ' + Math.floor(diff / 60) + 'm';
                if (diff < 86400) return 'hace ' + Math.floor(diff / 3600) + 'h';
                if (diff < 604800) return 'hace ' + Math.floor(diff / 86400) + 'd';
                return date.toLocaleDateString('es-AR');
            }
        
            // Cargar al iniciar
            document.addEventListener('DOMContentLoaded', function() {
                console.log('DOMContentLoaded de comunidad');
                window.cargarComunidad();
            });
        </script>

        
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
    
            :root {
                --verde: #104547;
                --verde-light: #1a6b6e;
                --crema: #fffff5;
                --gris: #f5f5f0;
                --gris-borde: #e8e8e0;
                --texto: #2a2a2a;
                --texto-suave: #777;
            }
    
            body {
                font-family: 'Montserrat', sans-serif;
                background: var(--gris);
                color: var(--texto);
                padding-top: 55px;
                padding-bottom: 70px;
            }
    
            /* ── HEADER ── */
            .app-header {
                background: #104547;
                height: 55px;
                position: fixed;
                top: 0; left: 0; right: 0;
                z-index: 1000;
                display: flex;
                align-items: center;
                justify-content: space-between;
                padding: 0 20px;
                box-shadow: 0 2px 8px rgba(0,0,0,0.15);
            }
            .app-header-logo { height: 40px; width: auto; }
            .app-header-contact { display: flex; gap: 15px; align-items: center; }
            .app-header-contact a {
                display: flex;
                align-items: center;
                justify-content: center;
                width: 32px;
                height: 32px;
                background: rgba(218, 198, 154, 0.2);
                border-radius: 50%;
                transition: all 0.2s;
            }
            .app-header-contact a:hover { background: #dac69a; }
            .app-header-contact img {
                width: 18px;
                height: 18px;
                filter: brightness(0) invert(1);
            }
            
            /* ── TÍTULO PÁGINA ── */
            .page-title {
                background: var(--verde);
                color: white;
                padding: 18px 20px 22px;
                text-align: center;
            }
            .page-title h1 {
                font-size: 20px;
                font-weight: 800;
                letter-spacing: -0.3px;
            }
            .page-title p {
                font-size: 12px;
                opacity: 0.7;
                margin-top: 3px;
                font-weight: 500;
            }
    
            /* ── CONTENEDOR PRINCIPAL ── */
            .comunidad-container {
                max-width: 640px;
                margin: 0 auto;
                padding: 16px 14px;
                display: flex;
                flex-direction: column;
                gap: 12px;
            }
    
            /* ── SECCIÓN COLAPSABLE ── */
            .seccion {
                background: white;
                border-radius: 16px;
                overflow: hidden;
                box-shadow: 0 1px 6px rgba(0,0,0,0.07);
            }
    
            .seccion-header {
                display: flex;
                align-items: center;
                justify-content: space-between;
                padding: 16px 18px;
                cursor: pointer;
                user-select: none;
                transition: background 0.15s;
            }
            .seccion-header:active { background: #f9f9f9; }
    
            .seccion-header-left {
                display: flex;
                align-items: center;
                gap: 10px;
            }
            .seccion-icon {
                width: 36px; height: 36px;
                background: var(--verde);
                border-radius: 10px;
                display: flex; align-items: center; justify-content: center;
                font-size: 17px;
                flex-shrink: 0;
            }
            .seccion-titulo {
                font-size: 15px;
                font-weight: 700;
                color: var(--verde);
            }
            .seccion-subtitulo {
                font-size: 11px;
                color: var(--texto-suave);
                margin-top: 1px;
            }
    
            .seccion-chevron {
                color: var(--texto-suave);
                font-size: 13px;
                transition: transform 0.25s ease;
            }
            .seccion.expandida .seccion-chevron { transform: rotate(180deg); }
    
            .seccion-divider {
                height: 1px;
                background: var(--gris-borde);
                margin: 0 18px;
            }
    
            /* ── CUERPO COLAPSABLE ── */
            .seccion-body {
                max-height: 0;
                overflow: hidden;
                transition: max-height 0.35s ease;
            }
            .seccion.expandida .seccion-body {
                max-height: 2000px;
            }
            .seccion-content { padding: 14px 16px 18px; }
    
            /* ── PREVIEW (siempre visible) ── */
            .seccion-preview {
                padding: 0 16px 14px;
            }
    
            /* ── COMENTARIOS ── */
            .comment-card {
                padding: 12px 0;
                border-bottom: 1px solid var(--gris-borde);
            }
            .comment-card:last-child { border-bottom: none; }
    
            .comment-meta {
                display: flex;
                align-items: center;
                gap: 8px;
                margin-bottom: 6px;
            }
            .comment-avatar {
                width: 30px; height: 30px;
                border-radius: 50%;
                background: var(--verde);
                display: flex; align-items: center; justify-content: center;
                color: white;
                font-size: 12px;
                font-weight: 700;
                flex-shrink: 0;
            }
            .comment-user { font-size: 12px; font-weight: 700; color: var(--verde); }
            .comment-cafe {
                font-size: 11px;
                color: var(--texto-suave);
                margin-left: auto;
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
                max-width: 130px;
            }
            .comment-text {
                font-size: 13px;
                color: #333;
                line-height: 1.5;
                padding-left: 38px;
            }
            .comment-tiempo {
                font-size: 10px;
                color: #bbb;
                padding-left: 38px;
                margin-top: 4px;
            }
    
            /* ── TOP CAFÉS ── */
            .ranking-item {
                display: flex;
                align-items: center;
                gap: 12px;
                padding: 10px 0;
                border-bottom: 1px solid var(--gris-borde);
            }
            .ranking-item:last-child { border-bottom: none; }
    
            .ranking-pos {
                font-size: 16px;
                font-weight: 800;
                color: #ddd;
                width: 24px;
                text-align: center;
                flex-shrink: 0;
            }
            .ranking-pos.gold   { color: #f6c90e; }
            .ranking-pos.silver { color: #b0b0b0; }
            .ranking-pos.bronze { color: #cd7f32; }
    
            .ranking-info { flex: 1; min-width: 0; }
            .ranking-nombre {
                font-size: 13px;
                font-weight: 600;
                color: var(--texto);
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
            }
            .ranking-barrio {
                font-size: 11px;
                color: var(--texto-suave);
                margin-top: 1px;
            }
            .ranking-count {
                display: flex;
                align-items: center;
                gap: 4px;
                font-size: 12px;
                font-weight: 700;
                color: var(--verde);
                flex-shrink: 0;
            }
    
            /* ── EXPLORADORES ── */
            .podio {
                display: flex;
                align-items: flex-end;
                justify-content: center;
                gap: 10px;
                padding: 10px 0 16px;
            }
            .podio-item {
                display: flex;
                flex-direction: column;
                align-items: center;
                gap: 6px;
                flex: 1;
            }
            .podio-avatar {
                border-radius: 50%;
                background: var(--verde);
                display: flex; align-items: center; justify-content: center;
                color: white;
                font-weight: 800;
                flex-shrink: 0;
            }
            .podio-item:nth-child(1) .podio-avatar { width: 52px; height: 52px; font-size: 20px; }
            .podio-item:nth-child(2) .podio-avatar { width: 44px; height: 44px; font-size: 17px; background: #1a6b6e; }
            .podio-item:nth-child(3) .podio-avatar { width: 38px; height: 38px; font-size: 15px; background: #2a8a8e; }
    
            .podio-corona { font-size: 18px; line-height: 1; }
            .podio-nombre { font-size: 11px; font-weight: 700; color: var(--texto); text-align: center; }
            .podio-count { font-size: 10px; color: var(--texto-suave); }
    
            .explorador-item {
                display: flex;
                align-items: center;
                gap: 10px;
                padding: 8px 0;
                border-bottom: 1px solid var(--gris-borde);
            }
            .explorador-item:last-child { border-bottom: none; }
            .explorador-num {
                font-size: 12px;
                font-weight: 700;
                color: #ccc;
                width: 20px;
                text-align: center;
            }
            .explorador-avatar {
                width: 32px; height: 32px;
                border-radius: 50%;
                background: var(--gris);
                border: 2px solid var(--gris-borde);
                display: flex; align-items: center; justify-content: center;
                font-size: 13px;
                font-weight: 700;
                color: var(--verde);
                flex-shrink: 0;
            }
            .explorador-nombre { font-size: 13px; font-weight: 600; flex: 1; }
            .explorador-count {
                font-size: 12px;
                font-weight: 700;
                color: var(--verde);
            }
    
            /* ── VER MÁS ── */
            .ver-mas-btn {
                width: 100%;
                padding: 11px;
                background: none;
                border: 1.5px solid var(--gris-borde);
                border-radius: 10px;
                font-size: 12px;
                font-weight: 600;
                color: var(--verde);
                cursor: pointer;
                margin-top: 10px;
                font-family: 'Montserrat', sans-serif;
                transition: background 0.15s;
            }
            .ver-mas-btn:hover { background: var(--gris); }
    
            /* ── BADGE PRÓXIMAMENTE ── */
            .pronto-badge {
                display: inline-flex;
                align-items: center;
                gap: 4px;
                background: #fff3cd;
                color: #856404;
                font-size: 10px;
                font-weight: 700;
                padding: 3px 8px;
                border-radius: 20px;
                margin-left: 8px;
            }
    
            /* ── NAVBAR ── */
            .bottom-navbar {
                position: fixed;
                bottom: 0; left: 0; right: 0;
                height: 60px;
                background: white;
                border-top: 1px solid var(--gris-borde);
                display: flex;
                justify-content: space-around;
                align-items: center;
                z-index: 1000;
            }
            .nav-item {
                display: flex;
                flex-direction: column;
                align-items: center;
                gap: 3px;
                cursor: pointer;
                text-decoration: none;
                color: #999;
                padding: 6px 20px;
                transition: color 0.2s;
            }
            .nav-item svg { width: 22px; height: 22px; }
            .nav-item span { font-size: 10px; font-weight: 600; }
            .nav-item.active { color: var(--verde); }
    
            /* ── EMPTY STATE ── */
            .empty-state {
                text-align: center;
                padding: 24px 0 8px;
                color: var(--texto-suave);
                font-size: 13px;
            }
            .empty-state .empty-icon { font-size: 32px; margin-bottom: 8px; }
    
            /* ── DESKTOP ── */
            @media (min-width: 640px) {
                .comunidad-container { padding: 20px 20px; }
                .seccion-titulo { font-size: 16px; }
                .comment-text { font-size: 14px; }
            }
        </style>
    </head>
    <body>
    
        <!-- Header -->
        <div class="app-header">
            <img src="/assets/buscafes_header2.png" alt="Buscafes" class="app-header-logo">
            <div class="app-header-contact">
                <a href="mailto:buscafes.ai@gmail.com">
                    <img src="https://jsonbuscafe.blob.core.windows.net/contbuscafe/envelope-solid.svg" alt="Email">
                </a>
                <a href="https://www.instagram.com/buscafes.ai" target="_blank">
                    <img src="https://jsonbuscafe.blob.core.windows.net/contbuscafe/instagram-brands-solid.svg" alt="Instagram">
                </a>
            </div>
        </div>
    
        <!-- Título -->
        <div class="page-title">
            <h1>☕ Comunidad</h1>
            <p>Lo que está pasando en Buscafes</p>
        </div>
    
        <!-- Contenido -->
        <div class="comunidad-container">
    
            <!-- SECCIÓN: Comentarios recientes -->
            <div class="seccion" id="sec-comentarios">
                <div class="seccion-header" onclick="toggleSeccion('sec-comentarios')">
                    <div class="seccion-header-left">
                        <div class="seccion-icon">💬</div>
                        <div>
                            <div class="seccion-titulo">Comentarios recientes</div>
                            <div class="seccion-subtitulo">Se anda diciendo...</div>
                        </div>
                    </div>
                    <span class="seccion-chevron">▼</span>
                </div>
    
                <!-- Preview (siempre visible) -->
                <div class="seccion-preview" id="preview-comentarios">
                    <!-- se llena con JS -->
                </div>
    
                <!-- Expandible -->
                <div class="seccion-body">
                    <div class="seccion-content" id="body-comentarios">
                        <!-- se llena con JS -->
                    </div>
                </div>
            </div>
    
            <!-- SECCIÓN: Top cafeterías -->
            <div class="seccion" id="sec-topcafes">
                <div class="seccion-header" onclick="toggleSeccion('sec-topcafes')">
                    <div class="seccion-header-left">
                        <div class="seccion-icon">🏆</div>
                        <div>
                            <div class="seccion-titulo">Top cafeterías</div>
                            <div class="seccion-subtitulo">Las más likeadas del mapa</div>
                        </div>
                    </div>
                    <span class="seccion-chevron">▼</span>
                </div>
    
                <div class="seccion-preview" id="preview-topcafes"></div>
    
                <div class="seccion-body">
                    <div class="seccion-content" id="body-topcafes"></div>
                </div>
            </div>
    
            <!-- SECCIÓN: Exploradores -->
            <div class="seccion" id="sec-exploradores">
                <div class="seccion-header" onclick="toggleSeccion('sec-exploradores')">
                    <div class="seccion-header-left">
                        <div class="seccion-icon">🧭</div>
                        <div>
                            <div class="seccion-titulo">Exploradores</div>
                            <div class="seccion-subtitulo">Los que más cafés visitaron</div>
                        </div>
                    </div>
                    <span class="seccion-chevron">▼</span>
                </div>
    
                <div class="seccion-preview" id="preview-exploradores"></div>
    
                <div class="seccion-body">
                    <div class="seccion-content" id="body-exploradores"></div>
                </div>
            </div>
    
            <!-- SECCIÓN: Eventos (próximamente) -->
            <div class="seccion" id="sec-eventos">
                <div class="seccion-header" onclick="toggleSeccion('sec-eventos')">
                    <div class="seccion-header-left">
                        <div class="seccion-icon">📅</div>
                        <div>
                            <div class="seccion-titulo">
                                Eventos
                                <span class="pronto-badge">✨ Próximamente</span>
                            </div>
                            <div class="seccion-subtitulo">Novedades de las cafeterías</div>
                        </div>
                    </div>
                    <span class="seccion-chevron">▼</span>
                </div>
    
                <div class="seccion-body">
                    <div class="seccion-content">
                        <div class="empty-state">
                            <div class="empty-icon">📅</div>
                            <p>Pronto vas a poder ver eventos,<br>promociones y novedades de tus cafeterías.</p>
                        </div>
                    </div>
                </div>
            </div>
    
        </div>
    
        <!-- Navbar -->
        <div class="bottom-navbar">
            <a href="/perfil" class="nav-item">
                <img src="/assets/icon_usuario.png" style="width:24px;height:24px;">
                <span>Perfil</span>
            </a>
            <a href="/" class="nav-item">
                <img src="/assets/icono_mapa.png" style="width:24px;height:24px;">
                <span>Mapa</span>
            </a>
            <a href="/comunidad" class="nav-item active">
                <img src="/assets/icono_comunidad2.png" style="width:24px;height:24px;">
                <span>Comunidad</span>
            </a>
        </div>
    
        <script>
            window.geoLookup = __GEO_LOOKUP__;
            function getDatos() {
                return {
                    comentarios: window._comunidadComentarios || [],
                    topCafes: window._comunidadTopCafes || [],
                    exploradores: window._comunidadExploradores || []
                };
            }
            
            function renderPreviews() {
                const { comentarios, topCafes, exploradores } = getDatos();
            
                document.getElementById('preview-comentarios').innerHTML =
                    comentarios.length > 0
                        ? comentarios.slice(0, 3).map(renderComentario).join('')
                        : '<div class="empty-state"><div class="empty-icon">💬</div><p>Todavía no hay comentarios públicos.</p></div>';
            
                document.getElementById('preview-topcafes').innerHTML =
                    topCafes.length > 0
                        ? topCafes.slice(0, 3).map((c, i) => renderRankingItem(c, i)).join('')
                        : '<div class="empty-state"><div class="empty-icon">🏆</div><p>Todavía no hay datos de favoritos.</p></div>';
            
                const top3 = exploradores.slice(0, 3);
                if (top3.length === 0) {
                    document.getElementById('preview-exploradores').innerHTML =
                        '<div class="empty-state"><div class="empty-icon">🧭</div><p>Todavía no hay exploradores.</p></div>';
                    return;
                }
                
                // Solo mostrar los que existen realmente
                const coronas = ['🥇', '🥈', '🥉'];
                const sizes = ['52px', '44px', '38px'];
                const fontSizes = ['20px', '17px', '15px'];
                
                // Orden visual del podio: 2do, 1ro, 3ro
                const podioIndices = top3.length === 1 ? [0] :
                                     top3.length === 2 ? [1, 0] : [1, 0, 2];
                
                document.getElementById('preview-exploradores').innerHTML = `
                    <div class="podio">
                        ${podioIndices.map(idx => {
                            const e = top3[idx];
                            return `
                                <div class="podio-item">
                                    <div class="podio-corona">${coronas[idx]}</div>
                                    <div class="podio-avatar" style="width:${sizes[idx]};height:${sizes[idx]};font-size:${fontSizes[idx]}">${inicial(e.user)}</div>
                                    <div class="podio-nombre">${e.user.length > 12 ? e.user.substring(0,12)+'…' : e.user}</div>
                                    <div class="podio-count">☕ ${e.visitas}</div>
                                </div>
                            `;
                        }).join('')}
                    </div>
                `;
            }
            
            function renderBodyExploradores() {
                const { exploradores } = getDatos();
                const miUsername = localStorage.getItem('buscafes_username');
                const miPos = exploradores.findIndex(e => e.user === miUsername);
                const resto = exploradores.slice(3);
            
                let html = resto.slice(0, 17).map((e, i) => renderExploradorItem(e, i + 3)).join('');
            
                // Si el usuario logueado no está en el top 20
                if (miUsername && miPos > 19) {
                    html += `
                        <div style="text-align:center;color:#ccc;padding:8px 0;font-size:18px">•••</div>
                        ${renderExploradorItem(exploradores[miPos], miPos, true)}
                        <div style="text-align:center;color:#ccc;padding:8px 0;font-size:18px">•••</div>
                    `;
                } else if (miUsername && miPos >= 3) {
                    // Ya está en el top 20, resaltarlo
                    html = resto.slice(0, 17).map((e, i) => renderExploradorItem(e, i + 3, e.user === miUsername)).join('');
                }
            
                document.getElementById('body-exploradores').innerHTML = html || '';
            }


            function renderBodies() {
                const { comentarios, topCafes } = getDatos();
            
                document.getElementById('body-comentarios').innerHTML =
                    comentarios.slice(3).map(renderComentario).join('') || '';
            
                document.getElementById('body-topcafes').innerHTML =
                    topCafes.slice(3).map((c, i) => renderRankingItem(c, i + 3)).join('') || '';
            
                renderBodyExploradores();
            }

            // ══════════════════════════════════════
            // HELPERS
            // ══════════════════════════════════════
            function inicial(nombre) {
                return nombre.replace(/[^a-zA-Z]/g, '').charAt(0).toUpperCase() || '?';
            }
    
            function renderComentario(c) {
                return `
                    <div class="comment-card">
                        <div class="comment-meta">
                            <div class="comment-avatar">${inicial(c.cafe)}</div>
                            <span class="comment-user" style="color:#333;font-size:13px;font-weight:700;">☕ ${c.cafe}</span>
                            <span class="comment-cafe" style="color:#104547;font-weight:600;">@${c.user}</span>
                        </div>
                        <div class="comment-text">${c.texto}</div>
                        <div class="comment-tiempo">${c.tiempo}</div>
                    </div>
                `;
            }
    
            function renderRankingItem(c, i) {
                const posClass = i === 0 ? 'gold' : i === 1 ? 'silver' : i === 2 ? 'bronze' : '';
                const posLabel = i === 0 ? '🥇' : i === 1 ? '🥈' : i === 2 ? '🥉' : `${i + 1}`;
                return `
                    <div class="ranking-item">
                        <div class="ranking-pos ${posClass}">${posLabel}</div>
                        <div class="ranking-info">
                            <div class="ranking-nombre">${c.nombre}</div>
                            ${c.dir ? `<div class="ranking-barrio">📍 ${c.dir}</div>` : ''}
                        </div>
                        <div class="ranking-count">❤️ ${c.favs}</div>
                    </div>
                `;
            }
    
            function renderExploradorItem(e, i, esYo = false) {
                return `
                    <div class="explorador-item" style="${esYo ? 'background:#f0f7f7;border-radius:8px;padding:8px;' : ''}">
                        <div class="explorador-num" style="${esYo ? 'color:#104547;font-weight:800;' : ''}">${i + 1}</div>
                        <div class="explorador-avatar" style="${esYo ? 'border-color:#104547;color:#104547;' : ''}">${inicial(e.user)}</div>
                        <div class="explorador-nombre" style="${esYo ? 'color:#104547;font-weight:700;' : ''}">${e.user}${esYo ? ' <span style="font-size:10px;background:#104547;color:white;padding:2px 6px;border-radius:10px;">Vos</span>' : ''}</div>
                        <div class="explorador-count">☕ ${e.visitas}</div>
                    </div>
                `;
            }
    
    
            // ══════════════════════════════════════
            // TOGGLE SECCIÓN
            // ══════════════════════════════════════
            function toggleSeccion(id) {
                const sec = document.getElementById(id);
                sec.classList.toggle('expandida');
            }
    
            // ══════════════════════════════════════
            // INIT
            // ══════════════════════════════════════
            renderPreviews();
            renderBodies();
        </script>
    
    </body>
    </html>
    '''
    return (html
    .replace("__FIREBASE_CONFIG_COMUNIDAD__", json.dumps(firebase_config_comunidad))
    .replace("__GEO_LOOKUP__", json.dumps(geo_lookup, ensure_ascii=False))
)

# Redirect www → sin www
@server.before_request
def redirect_www():
    from flask import request, redirect
    if request.host.startswith('www.'):
        scheme = request.headers.get('X-Forwarded-Proto', 'https')
        new_host = request.host.replace('www.', '', 1)
        url = f"{scheme}://{new_host}{request.full_path.rstrip('?')}"
        return redirect(url, code=301)


app._favicon = ("coffee-solid.ico")
# Habilitar la compresión
Compress(server)

# Agregar el atributo lang al elemento <html>
CLIENT_CONN = os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING", "")

# URL del archivo JSON comprimido en Azure
url = 'https://jsonbuscafe.blob.core.windows.net/contbuscafe/geojson_data45.json'

# Traer el contenido
response = requests.get(url)

response.raise_for_status()  # lanza error si algo falló

# Cargar el contenido ya descomprimido en un diccionario Python
geojson_data = orjson.loads(response.content)

#para el panel con los favoritos
def extraer_url(sitio_web):
    if not sitio_web or sitio_web == 'Sin datos':
        return ''
    match = re.search(r'href="([^"]+)"', sitio_web)
    return match.group(1) if match else sitio_web

geo_lookup = {
    str(f['properties']['id']): {
        'nombre': f['properties']['Nombre'],
        'dir':    f['properties']['Dirección'],
        'barrio': f['properties']['Barrio'],
        'web':    extraer_url(f['properties'].get('Sitio Web', ''))
    }
    for f in geojson_data['features']
}

app.index_string = """
<!DOCTYPE html>
<html lang="es">
<head>
  {%metas%}
  <title>{%title%}</title>
  {%favicon%}
  <link rel="icon" type="image/png" href="/assets/icono_cafeterias.png" sizes="32x32">
  <link rel="apple-touch-icon" href="/assets/icono_cafeterias.png">
  {%css%}
  
  <!-- CSS Crítico para render inicial -->
  <style>
    body { margin: 0; padding: 0; font-family: 'Montserrat', sans-serif; }
    .app-header { 
      background: #104547; 
      height: 55px; 
      position: fixed; 
      top: 0; left: 0; right: 0; 
      z-index: 2500;
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0 20px;
    }
    .bottom-navbar {
      position: fixed;
      bottom: 0;
      left: 0; right: 0;
      height: 65px;
      background: #ffffff;
      border-top: 1px solid #e0e0e0;
      display: flex;
      align-items: center;
      justify-content: space-around;
      z-index: 2700;
    }
    #loading-div {
      position: fixed;
      top: 0; left: 0;
      width: 100%; height: 100%;
      display: flex;
      justify-content: center;
      align-items: center;
      background: white;
      z-index: 3000;
    }
    .controls-container.hidden { display: none !important; }
    .login-overlay { display: none; }
    .user-menu { display: none; }
    #panel-guardados { display: none; }
    #panel-sugerencia { display: none; }
  </style>

  <link rel="preload" as="image" href="/assets/buscafes_header2.png" fetchpriority="high">
  <link rel="preload" as="font" type="font/woff2" href="/assets/Montserrat-Regular.woff2" crossorigin="anonymous">
  <link rel="preload" as="font" type="font/woff2" href="/assets/Montserrat-Bold.woff2" crossorigin="anonymous">
  <link rel="preconnect" href="https://a.basemaps.cartocdn.com" crossorigin="anonymous">
  <link rel="preconnect" href="https://b.basemaps.cartocdn.com" crossorigin="anonymous">
  <link rel="preconnect" href="https://c.basemaps.cartocdn.com" crossorigin="anonymous">

  <script defer src="https://js.monitor.azure.com/scripts/b/ai.2.min.js" crossorigin="anonymous"></script>
  <script defer type="text/javascript">
    document.addEventListener('DOMContentLoaded', function() {
        var appInsights = window.appInsights || new Microsoft.ApplicationInsights.ApplicationInsights({
            config: { connectionString: "__AI_CONN__", enableAutoRouteTracking: true }
        });
        appInsights.loadAppInsights();
        appInsights.trackPageView();
    });
  </script>
</head>
<body>
  <!-- Header -->
  <div class="app-header">
    <img src="/assets/buscafes_header2.png" alt="Buscafes" class="app-header-logo">
    <div class="app-header-contact">
      <a href="mailto:buscafes.ai@gmail.com" title="Email">
        <img src="https://jsonbuscafe.blob.core.windows.net/contbuscafe/envelope-solid.svg " alt="Email">
      </a>
      <a href="https://www.instagram.com/buscafes.ai " target="_blank" title="Instagram">
        <img src="https://jsonbuscafe.blob.core.windows.net/contbuscafe/instagram-brands-solid.svg " alt="Instagram">
      </a>
    </div>
  </div>

  <!-- App content -->
  <div class="app-content">
    <div id="react-entry-point">{%app_entry%}</div>
  </div>
  
  <!-- Bottom Navbar -->
  <div class="bottom-navbar">
    <button id="btn-nav-user" class="bottom-nav-btn" title="Usuario">
      <img src="/assets/icon_usuario.png" class="bottom-nav-icon" alt="Usuario">
      <div class="bottom-nav-label">Usuario</div>
    </button>
    <button id="btn-nav-saved" class="bottom-nav-btn" title="Mis cafeterías visitadas">
      <img src="/assets/icon_fav.png" class="bottom-nav-icon" alt="Favoritos">
      <div class="bottom-nav-label">Favoritos</div>
    </button>
    <button id="btn-nav-filters" class="bottom-nav-btn" title="Filtros">
      <img src="/assets/icon_filtros.png" class="bottom-nav-icon" alt="Filtros">
      <div class="bottom-nav-label">Filtros</div>
    </button>
    <button id="btn-nav-suggest" class="bottom-nav-btn" title="Sugerir cafetería">
      <img src="/assets/icon_sugerir.png" class="bottom-nav-icon" alt="Sugerir">
      <div class="bottom-nav-label">Sugerir</div>
    </button>
    <button id="btn-nav-locate" class="bottom-nav-btn" title="Mi ubicación">
      <img src="/assets/icon_ubicar.png" class="bottom-nav-icon" alt="Ubicar">
      <div class="bottom-nav-label">Ubicar</div>
    </button>
  </div>
  
  <!-- Overlay para cerrar paneles clickeando fuera -->
  <div id="panel-overlay" class="panel-overlay"></div>
  
  <footer>{%config%}{%scripts%}{%renderer%}</footer>

  <!-- Firebase SDK (único) -->
  <script type="module">
    async function initFirebase() {
        if (window.firebaseAuth) return;

        const { initializeApp } = await import('https://www.gstatic.com/firebasejs/10.8.0/firebase-app.js');
        const { getAuth, signInWithPopup, GoogleAuthProvider, createUserWithEmailAndPassword,
                signInWithEmailAndPassword, onAuthStateChanged, signOut } 
              = await import('https://www.gstatic.com/firebasejs/10.8.0/firebase-auth.js');
        const { getFirestore, doc, setDoc, getDoc, collection, getDocs, deleteDoc, 
                updateDoc, increment, query, where, orderBy, limit, addDoc, serverTimestamp } 
              = await import('https://www.gstatic.com/firebasejs/10.8.0/firebase-firestore.js');

        const firebaseConfig = __FIREBASE_CONFIG__;
        const app = initializeApp(firebaseConfig);
        const auth = getAuth(app);
        const db = getFirestore(app);

        window.firebaseAuth = auth;
        window.firebaseDb = db;
        window.firebaseUtils = { 
            signInWithPopup, GoogleAuthProvider, createUserWithEmailAndPassword,
            signInWithEmailAndPassword, onAuthStateChanged, signOut,
            doc, setDoc, getDoc, collection, getDocs, deleteDoc,
            updateDoc, increment, query, where, orderBy, limit, addDoc, serverTimestamp
        };
        window.userCafeData = JSON.parse(localStorage.getItem('buscafes_user_data') || '{}');

        async function cargarDatosUsuario(uid) {
            try {
                const { collection, getDocs } = window.firebaseUtils;
                const cafesSnap = await getDocs(
                    collection(window.firebaseDb, 'users', uid, 'cafes')
                );
                
                // Sin merge: Firestore gana siempre
                const firestoreData = {};
                cafesSnap.forEach(d => { firestoreData[d.id] = d.data(); });
                
                localStorage.setItem('buscafes_user_data', JSON.stringify(firestoreData));
                window.userCafeData = firestoreData;
                
                window.showToast('✓ Datos cargados', 2000);
            } catch (err) {
                console.warn('Error cargando datos del usuario:', err);
            }
        }

        onAuthStateChanged(auth, function(user) {
            const warning = document.getElementById('guest-warning');
            if (user) {
                if (warning) warning.style.display = 'none';
                onUserLogin(user);
            } else {
                if (warning) warning.style.display = 'block';
                onUserLogout();
            }
        });
        
        function onUserLogin(user) {
            const btnUser = document.getElementById('btn-nav-user');
            if (btnUser) {
                const iconImg = btnUser.querySelector('.bottom-nav-icon');
                if (iconImg) {
                    if (user.photoURL) {
                        iconImg.src = user.photoURL;
                        iconImg.style.borderRadius = '50%';
                        iconImg.style.objectFit = 'cover';
                    } else {
                        const initial = document.createElement('div');
                        initial.className = 'bottom-nav-icon';
                        initial.style.cssText = 'background:#104547;border-radius:50%;display:flex;align-items:center;justify-content:center;color:#fff;font-weight:700;font-size:14px;';
                        initial.textContent = user.email.charAt(0).toUpperCase();
                        iconImg.parentNode.replaceChild(initial, iconImg);
                    }
                }
            }
            localStorage.setItem('buscafes_user_email', user.email);
            const existingUsername = localStorage.getItem('buscafes_username');
            const esNombreAnonimo = !existingUsername || 
                existingUsername.startsWith('anon_') ||
                /^(Barista|Cortado|Lágrima|Espresso|Ristretto|Macchiato|Affogato|Mocha|Capuchino|FlatWhite)An[oó]nim[oa]\d+$/.test(existingUsername);
        
            if (esNombreAnonimo) {
                // Guardar el nombre anónimo para restaurarlo al deslogear
                if (existingUsername) localStorage.setItem('buscafes_anon_username', existingUsername);
                const suggested = user.displayName || user.email.split('@')[0];
                localStorage.setItem('buscafes_username', suggested);
                window.syncUsernameFirestore?.(suggested);
                setTimeout(() => window.showToast('¡Bienvenido a Buscafes, ' + suggested + '! 👋', 3000), 500);
            }
            const emailDiv = document.getElementById('profile-user-email');
            if (emailDiv) emailDiv.textContent = user.email;
            const overlay = document.getElementById('login-overlay');
            if (overlay) overlay.style.display = 'none';
        
            cargarDatosUsuario(user.uid);
        }
        
        function onUserLogout() {
            const wasLoggedIn = localStorage.getItem('buscafes_user_email');
            
            if (wasLoggedIn) {
                localStorage.removeItem('buscafes_user_data');
                localStorage.removeItem('buscafes_user_email');
                window.userCafeData = {};
        
                // Restaurar nombre anónimo si existía, si no borrar
                const anonName = localStorage.getItem('buscafes_anon_username');
                if (anonName) {
                    localStorage.setItem('buscafes_username', anonName);
                } else {
                    localStorage.removeItem('buscafes_username');
                }
            }
        
            // Reset del ícono siempre
            const btnUser = document.getElementById('btn-nav-user');
            if (btnUser) {
                const iconElement = btnUser.querySelector('.bottom-nav-icon');
                if (iconElement && iconElement.tagName !== 'IMG') {
                    const img = document.createElement('img');
                    img.src = '/assets/icon_usuario.png';
                    img.className = 'bottom-nav-icon';
                    img.alt = 'Usuario';
                    iconElement.parentNode.replaceChild(img, iconElement);
                } else if (iconElement) {
                    iconElement.src = '/assets/icon_usuario.png';
                    iconElement.style.borderRadius = '';
                    iconElement.style.objectFit = '';
                }
            }
        }

        async function syncLocalToFirebase(userId) {
            return; // Deshabilitado — datos se sincronizan en tiempo real
        }
    }

    function showLoginError(message) {
        const errorDiv = document.getElementById('login-error');
        if (errorDiv) {
            errorDiv.textContent = message;
            setTimeout(() => errorDiv.textContent = '', 5000);
        }
    }

    window.initFirebase = initFirebase;
  </script>

  <!-- UI Logic -->
  <script>
    window.buscafesLookup = __GEO_LOOKUP__;

    window.getCafeData = function(id) {
        const data = JSON.parse(localStorage.getItem('buscafes_user_data') || '{}');
        return data[id] || {
            isFavorite: false, isVisited: false, visitCount: 0, rating: 0,
            comment: '', isCommentPublic: false, priceRange: '', lastVisit: null
        };
    };
    
    window.saveCafeData = function(id, newData) {
        const data = JSON.parse(localStorage.getItem('buscafes_user_data') || '{}');
        if (!data[id]) data[id] = {};
        Object.assign(data[id], newData);
        localStorage.setItem('buscafes_user_data', JSON.stringify(data));
        window.userCafeData = data;
    };

    window.getOrCreateAnonId = function() {
        let id = localStorage.getItem('buscafes_anon_id');
        if (!id) {
            id = 'anon_' + Math.random().toString(36).substring(2, 15) 
                         + Math.random().toString(36).substring(2, 15);
            localStorage.setItem('buscafes_anon_id', id);
        }
        return id;
    };
    
    window.getActiveUid = function() {
        if (window.firebaseAuth?.currentUser) {
            return window.firebaseAuth.currentUser.uid;
        }
        return window.getOrCreateAnonId();
    };
    
    window.getActiveUsername = function() {
        return localStorage.getItem('buscafes_username') || window.getOrCreateAnonId();
    };


    window.syncUsernameFirestore = async function(nuevoNombre) {
        if (!window.firebaseDb) return;
        const { collection, query, where, getDocs, updateDoc, doc, setDoc } = window.firebaseUtils;
        const uid = window.getActiveUid();
    
        try {
            await setDoc(doc(window.firebaseDb, 'users', uid),
                { username: nuevoNombre },
                { merge: true }
            );
            const q = query(
                collection(window.firebaseDb, 'comentarios'),
                where('uid', '==', uid)
            );
            const snap = await getDocs(q);
            snap.forEach(async (d) => {
                await updateDoc(d.ref, { username: nuevoNombre });
            });
        } catch (err) {
            console.warn('Firestore username sync error:', err);
        }
    };

    window.showToast = function(msg, duration = 2500) {
        let toast = document.getElementById('bc-toast');
        if (!toast) {
            toast = document.createElement('div');
            toast.id = 'bc-toast';
            toast.style.cssText = `
                position: fixed;
                bottom: 80px;
                left: 50%;
                transform: translateX(-50%);
                background: #104547;
                color: #fffff5;
                padding: 10px 20px;
                border-radius: 20px;
                font-size: 13px;
                font-weight: 600;
                z-index: 9999;
                opacity: 0;
                transition: opacity 0.3s ease;
                pointer-events: none;
                white-space: nowrap;
            `;
            document.body.appendChild(toast);
        }
        toast.textContent = msg;
        clearTimeout(window._bcToastTimeout);
        toast.style.opacity = '1';
        window._bcToastTimeout = setTimeout(() => { toast.style.opacity = '0'; }, duration);
    };


    document.addEventListener('DOMContentLoaded', function() {
      const overlay = document.getElementById('panel-overlay');
      let isProcessingClick = false;

      (function initZoomMessage() {
        const msg = document.getElementById('zoom-message');
        if (!msg) return;
    
        const views = parseInt(localStorage.getItem('buscafes_zoom_msg') || '0');
        if (views >= 3) {
          msg.style.display = 'none';
          return;
        }
    
       // Esperar a que el loading-div se oculte
        const loadingDiv = document.getElementById('loading-div');
        const observer = new MutationObserver(function() {
          if (loadingDiv.style.display === 'none') {
            observer.disconnect();
            localStorage.setItem('buscafes_zoom_msg', views + 1);
            setTimeout(() => { msg.style.display = 'none'; }, 4000);
          }
        });
        observer.observe(loadingDiv, { attributes: true, attributeFilter: ['style'] });
      })();

      
      function isAnyPanelOpen() {
        return (
          (document.getElementById('filters-panel')?.classList.contains('visible')) ||
          (document.getElementById('panel-guardados')?.style.display === 'block') ||
          (document.getElementById('panel-sugerencia')?.style.display === 'block') ||
          (document.getElementById('profile-dropdown-container')?.style.display === 'block') ||
          (document.getElementById('login-overlay')?.style.display === 'flex') ||
          (document.getElementById('user-menu')?.style.display === 'block')
        );
      }
      
      function updateOverlay() {
        if (overlay) {
          overlay.classList.toggle('active', isAnyPanelOpen());
        }
      }
      
      function closeAllPanels() {
        const panels = {
          'filters-panel': { el: document.getElementById('filters-panel'), btn: 'btn-nav-filters', isClass: true },
          'panel-guardados': { el: document.getElementById('panel-guardados'), btn: 'btn-nav-saved' },
          'panel-sugerencia': { el: document.getElementById('panel-sugerencia'), btn: 'btn-nav-suggest' },
          'login-overlay': { el: document.getElementById('login-overlay'), btn: 'btn-nav-user' },
          'profile-dropdown-container': { el: document.getElementById('profile-dropdown-container'), btn: 'btn-nav-user' },
          'user-menu': { el: document.getElementById('user-menu'), btn: 'btn-nav-user' }
        };
        
        Object.entries(panels).forEach(([id, config]) => {
          if (config.el) {
            if (config.isClass) {
              config.el.classList.remove('visible');
              config.el.classList.add('hidden');
            } else {
              config.el.style.display = 'none';
            }
          }
          const btn = document.getElementById(config.btn);
          if (btn) btn.classList.remove('active');
        });
        
        setTimeout(updateOverlay, 30);
      }
      
      function closeOtherPanels(exceptId) {
        const allPanels = ['filters-panel', 'panel-guardados', 'panel-sugerencia', 'login-overlay', 'profile-dropdown-container', 'user-menu'];
        allPanels.forEach(id => {
          if (id !== exceptId) {
            const el = document.getElementById(id);
            if (el) {
              if (id === 'filters-panel') {
                el.classList.remove('visible');
                el.classList.add('hidden');
              } else {
                el.style.display = 'none';
              }
            }
          }
        });
        updateOverlay();
      }
      
      document.addEventListener('click', async function(e) {

        if (e.target.closest('#btn-google-login')) {
            e.preventDefault();
            if (!window.firebaseAuth) await window.initFirebase();
            try {
                const { signInWithPopup, GoogleAuthProvider } = window.firebaseUtils;
                await signInWithPopup(window.firebaseAuth, new GoogleAuthProvider());
            } catch (error) {
                const errorDiv = document.getElementById('login-error');
                if (errorDiv) errorDiv.textContent = 'Error al iniciar sesión con Google';
            }
        }
    
        // Email login
        if (e.target.id === 'btn-email-login') {
            if (!window.firebaseAuth) await window.initFirebase();
            const email = document.getElementById('login-email').value;
            const password = document.getElementById('login-password').value;
            if (!email || !password) {
                const errorDiv = document.getElementById('login-error');
                if (errorDiv) errorDiv.textContent = 'Completá todos los campos';
                return;
            }
            try {
                const { signInWithEmailAndPassword } = window.firebaseUtils;
                await signInWithEmailAndPassword(window.firebaseAuth, email, password);
            } catch (error) {
                const errorDiv = document.getElementById('login-error');
                if (errorDiv) errorDiv.textContent = 'Email o contraseña incorrectos';
            }
        }
    
        // Email signup
        if (e.target.id === 'btn-email-signup') {
            if (!window.firebaseAuth) await window.initFirebase();
            const name = document.getElementById('signup-name').value;
            const email = document.getElementById('signup-email').value;
            const password = document.getElementById('signup-password').value;
            if (!name || !email || !password) {
                const errorDiv = document.getElementById('login-error');
                if (errorDiv) errorDiv.textContent = 'Completá todos los campos';
                return;
            }
            if (password.length < 6) {
                const errorDiv = document.getElementById('login-error');
                if (errorDiv) errorDiv.textContent = 'Mínimo 6 caracteres';
                return;
            }
            try {
                const { createUserWithEmailAndPassword, doc, setDoc } = window.firebaseUtils;
                await createUserWithEmailAndPassword(window.firebaseAuth, email, password);
                const username = name.trim();
                localStorage.setItem('buscafes_username', username);
                await setDoc(doc(window.firebaseDb, 'users', window.firebaseAuth.currentUser.uid), 
                    { name, email, username, createdAt: new Date().toISOString() });
            } catch (error) {
                const errorDiv = document.getElementById('login-error');
                if (errorDiv) errorDiv.textContent = error.code === 'auth/email-already-in-use' 
                    ? 'Email ya registrado' : 'Error al crear cuenta';
            }
        }
      });
      document.addEventListener('click', async function(e) {
        const btn = e.target.closest('[id^="btn-nav-"]');
        if (!btn) return;
        const id = btn.id;
        if (id === 'btn-nav-saved') {
            const panel = document.getElementById('panel-guardados');
            if (!panel) return;
            const isVisible = panel.style.display === 'block';
            closeOtherPanels(isVisible ? null : 'panel-guardados');
            panel.style.display = isVisible ? 'none' : 'block';
            btn.classList.toggle('active', !isVisible);
            updateOverlay();
        }
    
        if (id === 'btn-nav-suggest') {
            const panel = document.getElementById('panel-sugerencia');
            if (!panel) return;
            const isVisible = panel.style.display === 'block';
            closeOtherPanels(isVisible ? null : 'panel-sugerencia');
            panel.style.display = isVisible ? 'none' : 'block';
            btn.classList.toggle('active', !isVisible);
            updateOverlay();
        }
    
        if (id === 'btn-nav-filters') {
            const panel = document.getElementById('filters-panel');
            if (!panel) return;
            const isVisible = panel.classList.contains('visible');
            closeOtherPanels(isVisible ? null : 'filters-panel');
            panel.classList.toggle('visible', !isVisible);
            panel.classList.toggle('hidden', isVisible);
            btn.classList.toggle('active', !isVisible);
            updateOverlay();
        }
    
        if (id === 'btn-nav-user') {
            e.stopPropagation();
            await window.initFirebase();
            const userMenu = document.getElementById('user-menu');
            if (!userMenu) return;
            const isVisible = userMenu.style.display === 'block';
            closeOtherPanels(isVisible ? null : 'user-menu');
        
            if (!isVisible) {
                // ← estas dos líneas faltaban
                const nombreEl = document.getElementById('user-menu-nombre');
                if (nombreEl) {
                    const username = localStorage.getItem('buscafes_username') || 
                                     localStorage.getItem('buscafes_user_email')?.split('@')[0] || 
                                     'USUARIO';
                    nombreEl.textContent = username;
                }
                updateMenuState();  // ← esto activa el botón Logearme/Deslogearme
            }
        
            userMenu.style.display = isVisible ? 'none' : 'block';
            btn.classList.toggle('active', !isVisible);
            updateOverlay();
        }
    
        if (id === 'btn-nav-locate') {
            const locateControl = document.querySelector('.leaflet-control-locate a');
            if (locateControl) {
                locateControl.click();
                btn.classList.add('active');
                setTimeout(() => btn.classList.remove('active'), 2000);
            }
        }
      });
      
      function updateMenuState() {
        const menuAuthAction = document.getElementById('menu-auth-action');
        if (!menuAuthAction) return;
        const isLoggedIn = window.firebaseAuth?.currentUser || 
                   localStorage.getItem('buscafes_user_email');
        const btnUser = document.getElementById('btn-nav-user');  // ← definilo acá
    
        if (isLoggedIn) {
            menuAuthAction.textContent = "Deslogearme";
            menuAuthAction.style.color = "#ff6b6b";
            menuAuthAction.onclick = function() {
                document.getElementById('user-menu').style.display = 'none';
                btnUser?.classList.remove('active');  // ← el ?. es por seguridad
                window.firebaseUtils?.signOut(window.firebaseAuth).then(() => {
                    window.showToast('✓ Sesión cerrada');
                    const icon = btnUser?.querySelector('.bottom-nav-icon');
                    if (icon) {
                        icon.src = '/assets/icon_usuario.png';
                        icon.style.borderRadius = '';
                    }
                    updateOverlay();
                });
            };
        } else {
          menuAuthAction.textContent = "Logearme";
          menuAuthAction.style.color = "#104547";
          menuAuthAction.onclick = function() {
            document.getElementById('user-menu').style.display = 'none';
            btnUser.classList.remove('active');
            const loginOverlay = document.getElementById('login-overlay');
            if (loginOverlay) {
              loginOverlay.style.display = 'flex';
              updateOverlay();
            }
          };
        }
      }
      
      // "Click fuera para cerrar"
      document.addEventListener('click', function(e) {
        const btnUser = document.getElementById('btn-nav-user');
        const userMenu = document.getElementById('user-menu');
        if (userMenu?.style.display === 'block' && !userMenu.contains(e.target) && e.target !== btnUser && !btnUser?.contains(e.target)) {
          userMenu.style.display = 'none';
          btnUser?.classList.remove('active');
          updateOverlay();
        }
      });
      
      // Ubicar
      const btnLocate = document.getElementById('btn-nav-locate');
      if (btnLocate) {
        btnLocate.addEventListener('click', function() {
            if (!navigator.geolocation) {
                window.showToast('Tu dispositivo no soporta geolocalización');
                return;
            }
            btnLocate.classList.add('active');
            navigator.geolocation.getCurrentPosition(
                function(position) {
                    const lat = position.coords.latitude;
                    const lng = position.coords.longitude;
                    // Buscar el mapa de Leaflet y centrarlo
                    const mapEl = document.querySelector('.leaflet-container');
                    if (mapEl && mapEl._leaflet_map) {
                        mapEl._leaflet_map.setView([lat, lng], 15, {animate: true});
                        // Agregar marcador de posición
                        const existing = window._userLocationMarker;
                        if (existing) existing.remove();
                        window._userLocationMarker = L.circleMarker([lat, lng], {
                            radius: 8,
                            fillColor: '#104547',
                            color: 'white',
                            weight: 2,
                            fillOpacity: 0.9
                        }).addTo(mapEl._leaflet_map);
                    }
                    btnLocate.classList.remove('active');
                },
                function(error) {
                    window.showToast('No se pudo obtener tu ubicación');
                    btnLocate.classList.remove('active');
                },
                { enableHighAccuracy: true, timeout: 10000 }
            );
          });
      }

      // Auto-inicializar Firebase en background
      setTimeout(function() {
        if (typeof window.initFirebase === 'function' && !window.firebaseDb) {
            window.initFirebase().catch(() => {});
        }
      }, 1500);

      // Overlay click
      if (overlay) {
        overlay.addEventListener('click', closeAllPanels);
      }
      
      // Global Observer (único)
      const globalObserver = new MutationObserver(function(mutations) {
        mutations.forEach(function(mutation) {
          if (mutation.attributeName === 'style') {
            const target = mutation.target;
            if (['panel-guardados', 'panel-sugerencia', 'profile-dropdown-container', 'login-overlay', 'user-menu'].includes(target.id)) {
              updateOverlay();
            }
          }
        });
      });
      
      globalObserver.observe(document.body, { 
        childList: false, 
        attributes: true, 
        attributeFilter: ['style'],
        subtree: true 
      });
      
      // Event delegation para cerrar con X
      document.addEventListener('click', function(e) {
        const target = e.target.closest('button');
        if (!target) return;
        
        const actions = {
          'btn-cerrar-login': () => {
            document.getElementById('login-overlay').style.display = 'none';
            document.getElementById('btn-nav-user')?.classList.remove('active');
          },

          'close-message-button': () => {  // ← nuevo
            document.getElementById('zoom-message').style.display = 'none';
            localStorage.setItem('buscafes_zoom_msg', '99'); // ← no vuelve a aparecer
          },
                  
          'btn-cerrar-guardados': () => {
            document.getElementById('panel-guardados').style.display = 'none';
            document.getElementById('btn-nav-saved')?.classList.remove('active');
          },
          'btn-cerrar-panel': () => {
            document.getElementById('panel-sugerencia').style.display = 'none';
            document.getElementById('btn-nav-suggest')?.classList.remove('active');
          },
          'btn-cerrar-filtros': () => {
            const panel = document.getElementById('filters-panel');
            panel?.classList.remove('visible');
            panel?.classList.add('hidden');
            document.getElementById('btn-nav-filters')?.classList.remove('active');
          },
          'btn-cerrar-user-menu': () => {
            document.getElementById('user-menu').style.display = 'none';
            document.getElementById('btn-nav-user')?.classList.remove('active');
          }
        };
        
        if (actions[target.id]) {
          e.stopPropagation();
          e.preventDefault();
          actions[target.id]();
          updateOverlay();
        }
      });
      
      // Link login from guest
      const linkLoginFromGuest = document.getElementById('link-login-from-guest');
      if (linkLoginFromGuest) {
        linkLoginFromGuest.addEventListener('click', function(e) {
          e.preventDefault();
          document.getElementById('panel-guardados').style.display = 'none';
          document.getElementById('btn-nav-saved')?.classList.remove('active');
          closeOtherPanels('login-overlay');
          setTimeout(() => {
            document.getElementById('btn-login')?.click();
            updateOverlay();
          }, 50);
        });
      }
    });
  </script>

  <!-- Funciones de utilidad para popups y panel -->
  <script>
    // Sistema de mini-modal para notas
    window.openNoteModal = function(id, nombre) {
        if (!nombre) nombre = (window.buscafesLookup[id] && window.buscafesLookup[id].nombre) || id;
        const data = window.getCafeData(id);
        const overlay = document.createElement('div');
        overlay.className = 'note-modal-overlay';
        overlay.innerHTML = `
            <div class="note-modal" style="max-width: 70%; width: 45%;">
                <div class="note-modal-header">
                    <div class="note-modal-title">Nota para ${nombre}</div>
                    <button class="note-modal-close" onclick="window.closeNoteModal()">×</button>
                </div>
                <textarea id="note-modal-textarea" class="note-modal-textarea" placeholder="¿Qué pediste? ¿Cómo fue la atención?">${data.comment || ''}</textarea>
                <div class="note-modal-footer">
                    <label class="note-modal-public">
                        <input type="checkbox" id="note-modal-public" ${data.isCommentPublic ? 'checked' : ''}>
                        <span>Hacer pública</span>
                    </label>
                    <button class="note-modal-save" onclick="window.saveNoteFromModal('${id}', '${nombre.replace(/'/g, "\\'")}')">Guardar</button>
                </div>
            </div>
        `;
        document.body.appendChild(overlay);
        setTimeout(() => document.getElementById('note-modal-textarea')?.focus(), 100);
    
        window._noteHandleEsc = (e) => { if (e.key === 'Escape') window.closeNoteModal(); };
        document.addEventListener('keydown', window._noteHandleEsc);
        overlay.addEventListener('click', (e) => { if (e.target === overlay) window.closeNoteModal(); });
    };
    
    window.closeNoteModal = function() {
      const overlay = document.querySelector('.note-modal-overlay');
      if (overlay) {
        overlay.remove();
        document.removeEventListener('keydown', window._noteHandleEsc);
      }
    };
    
    window.saveNoteFromModal = function(id, nombre) {
        const textarea = document.getElementById('note-modal-textarea');
        const checkbox = document.getElementById('note-modal-public');
        if (textarea && checkbox) {
            const newData = {
                comment: textarea.value,
                isCommentPublic: checkbox.checked,
                lastVisit: new Date().toISOString()
            };
            window.saveCafeData(id, newData);
            window.syncComentarioFirestore(id, nombre, textarea.value, checkbox.checked);
    
            if (window.firebaseDb && window.firebaseAuth?.currentUser) {
                const { doc, setDoc } = window.firebaseUtils;
                const uid = window.getActiveUid();
                setDoc(doc(window.firebaseDb, 'users', uid, 'cafes', id),
                    { comment: textarea.value, isCommentPublic: checkbox.checked },
                    { merge: true }
                ).catch(err => console.warn('Firestore note error:', err));
            }
    
            const btn = event.target;
            window.showToast('✓ Nota guardada');
            btn.style.background = '#28a745';
            setTimeout(() => {
                window.closeNoteModal();
                const panel = document.getElementById('panel-guardados');
                if (panel?.style.display !== 'none') window.abrirPanelGuardados?.();
            }, 1000);
        }
    };

    window.toggleFavorito = function(id, nombre) {
        if (!nombre) nombre = (window.buscafesLookup[id] && window.buscafesLookup[id].nombre) || id;
        const data = window.getCafeData(id);
        const newFav = !data.isFavorite;
        const yaVisitado = data.isVisited;
        const newData = {
            isFavorite: newFav,
            isVisited: true,
            nombre: nombre,
            visitCount: data.visitCount || (newFav ? 1 : 0),
            lastVisit: newFav ? new Date().toISOString() : data.lastVisit
        };
        window.saveCafeData(id, newData);
    
        const btn = document.getElementById('btn-fav-' + id);
        if (btn) {
            btn.innerHTML = (newFav ? '❤️' : '🤍') + ' Favorito';
            btn.classList.toggle('active', newFav);
        }
        if (newFav) {
            const btnVist = document.getElementById('btn-vist-' + id);
            if (btnVist) {
                btnVist.innerHTML = '✅ Visitado';
                btnVist.classList.add('active');
            }
        }
    
        const panel = document.getElementById('panel-guardados');
        if (panel?.style.display !== 'none') window.abrirPanelGuardados?.();
    
        if (!window.firebaseDb || !window.firebaseAuth?.currentUser) return;
        const { doc, setDoc, getDoc, increment } = window.firebaseUtils;
        const uid = window.getActiveUid();
    
        // Contador global del café
        setDoc(doc(window.firebaseDb, 'cafes', id),
            { favCount: increment(newFav ? 1 : -1), nombre: nombre },
            { merge: true }
        ).catch(err => console.warn('Firestore favCount error:', err));
    
        // visitCount del usuario — solo si el café no estaba ya visitado
        if (!yaVisitado) {
            if (newFav) {
                setDoc(doc(window.firebaseDb, 'users', uid), {
                    username: window.getActiveUsername(),
                    visitCount: increment(1)
                }, { merge: true }).catch(err => console.warn('Firestore user visitCount error:', err));
            } else {
                const userRef = doc(window.firebaseDb, 'users', uid);
                getDoc(userRef).then(snap => {
                    const currentCount = snap.data()?.visitCount || 0;
                    if (currentCount > 0) {
                        setDoc(userRef, {
                            username: window.getActiveUsername(),
                            visitCount: increment(-1)
                        }, { merge: true }).catch(err => console.warn('Firestore user visitCount error:', err));
                    }
                });
            }
        }
    
        // Datos del usuario por café
        setDoc(doc(window.firebaseDb, 'users', uid, 'cafes', id),
            newData,
            { merge: true }
        ).catch(err => console.warn('Firestore user cafe error:', err));
    };
    
    window.toggleVisitado = function(id, nombre) {
        if (!nombre) nombre = (window.buscafesLookup[id] && window.buscafesLookup[id].nombre) || id;
        const data = window.getCafeData(id);
        const newVist = !data.isVisited;
        const yaFavorito = data.isFavorite;
        const newData = {
            isVisited: newVist,
            nombre: nombre,
            visitCount: newVist ? (data.visitCount || 0) + 1 : Math.max(0, (data.visitCount || 1) - 1),
            lastVisit: newVist ? new Date().toISOString() : data.lastVisit
        };
        window.saveCafeData(id, newData);
    
        const btn = document.getElementById('btn-vist-' + id);
        if (btn) {
            btn.innerHTML = (newVist ? '✅' : '📍') + ' Visitado';
            btn.classList.toggle('active', newVist);
        }
        const panel = document.getElementById('panel-guardados');
        if (panel?.style.display !== 'none') window.abrirPanelGuardados?.();
    
        if (!window.firebaseDb || !window.firebaseAuth?.currentUser) return;
        const { doc, setDoc, getDoc, increment } = window.firebaseUtils;
        const uid = window.getActiveUid();
    
        // Contador global del café
        setDoc(doc(window.firebaseDb, 'cafes', id),
            { visitCount: increment(newVist ? 1 : -1), nombre: nombre },
            { merge: true }
        ).catch(err => console.warn('Firestore cafe visitCount error:', err));
    
        // visitCount del usuario — solo si el café no estaba ya como favorito
        if (!yaFavorito) {
            if (newVist) {
                setDoc(doc(window.firebaseDb, 'users', uid), {
                    username: window.getActiveUsername(),
                    visitCount: increment(1)
                }, { merge: true }).catch(err => console.warn('Firestore user visitCount error:', err));
            } else {
                const userRef = doc(window.firebaseDb, 'users', uid);
                getDoc(userRef).then(snap => {
                    const currentCount = snap.data()?.visitCount || 0;
                    if (currentCount > 0) {
                        setDoc(userRef, {
                            username: window.getActiveUsername(),
                            visitCount: increment(-1)
                        }, { merge: true }).catch(err => console.warn('Firestore user visitCount error:', err));
                    }
                });
            }
        }
    
        // Datos del usuario por café
        setDoc(doc(window.firebaseDb, 'users', uid, 'cafes', id),
            newData,
            { merge: true }
        ).catch(err => console.warn('Firestore user cafe error:', err));
    };

    let scCurrentFilter = 'all';
    
    window.abrirPanelGuardados = function(filterText) {
        filterText = (filterText || '').toLowerCase().trim();
        const userData = JSON.parse(localStorage.getItem('buscafes_user_data') || '{}');
        window.userCafeData = userData;
    
        let allIds = scCurrentFilter === 'fav'
            ? Object.keys(userData).filter(id => userData[id].isFavorite)
            : Object.keys(userData).filter(id => userData[id].isVisited || userData[id].isFavorite);
    
        allIds.sort((a, b) => {
            const na = userData[a].nombre || a;
            const nb = userData[b].nombre || b;
            return na.localeCompare(nb, 'es', { sensitivity: 'base' });
        });
    
        if (filterText) allIds = allIds.filter(id => {
            const nombre = userData[id].nombre || '';
            return nombre.toLowerCase().includes(filterText);
        });
    
        const container = document.getElementById('saved-list-container');
        if (!container) return;
    
        if (allIds.length === 0) {
            let emptyMsg = 'Todavía no guardaste ninguna cafetería.<br>¡Explorá el mapa y marcá tus favoritas!';
            if (scCurrentFilter === 'fav') emptyMsg = 'No tenés favoritas aún.';
            if (filterText) emptyMsg = 'No se encontraron resultados.';
            container.innerHTML = `<div class="sc-empty"><span class="sc-empty-icon">☕</span><p>${emptyMsg}</p></div>`;
            return;
        }
    
        container.innerHTML = allIds.map(id => {
            const data = userData[id] || {};
            const nombre = data.nombre || id;
            const geoData = (window.buscafesLookup || {})[id] || {};
            const safeId = id;
            const safeNombre = nombre.replace(/'/g, "\\'");
            const isFav = data.isFavorite === true;
            const isClosed = !geoData.dir && !geoData.barrio;
            const closedBadge = isClosed ? ' <span style="color:#ff6b6b;font-size:10px;font-weight:normal">❌ Cerró</span>' : '';
            const noteBadge = data.comment?.trim() ? '<span style="color:#104547;font-size:12px;margin-left:4px" title="Tiene nota">📝</span>' : '';
            const visitBadge = data.visitCount > 1 ? `<span style="background:#104547;color:white;font-size:10px;padding:2px 6px;border-radius:10px;margin-left:6px">${data.visitCount}x</span>` : '';
    
            return `
                <div class="sc-card${isClosed ? ' sc-card-closed' : ''}" data-id="${safeId}">
                    <div class="sc-card-main" onclick="this.parentElement.querySelector('.sc-detail').style.display = this.parentElement.querySelector('.sc-detail').style.display === 'none' ? 'block' : 'none'; this.parentElement.classList.toggle('expanded');">
                        <span class="sc-icons">${isFav ? '❤️' : '✅'}</span>
                        <span class="sc-name">${nombre}${closedBadge}${noteBadge}${visitBadge}</span>
                        <div class="sc-card-btns">
                            <button class="sc-heart-btn" onclick="event.stopPropagation(); window.toggleFavorito('${safeId}', '${safeNombre}');" title="${isFav ? 'Quitar de favoritos' : 'Agregar a favoritos'}">${isFav ? '❤️' : '🤍'}</button>
                            <button class="sc-del-btn" onclick="event.stopPropagation(); window.scRemove('${safeId}');" title="Quitar de la lista">✕</button>
                        </div>
                    </div>
                    <div class="sc-detail" style="display:none">
                        ${isClosed ? '<p style="color:#ff6b6b;font-style:italic">Esta cafetería cerró.</p>' :
                            (geoData.dir ? `<p>📍 <span>${geoData.dir}</span></p>` : '') +
                            (geoData.barrio ? `<p>🏘️ <span>${geoData.barrio}</span></p>` : '')}
                        <div class="sc-note-section" style="margin-top:12px;padding-top:12px;border-top:1px solid #eee;">
                            <div style="font-size:12px;color:#666;margin-bottom:6px;">📝 Tu nota:</div>
                            <textarea class="sc-note-input" placeholder="¿Qué pediste?..." onblur="window.scSaveNote('${safeId}', this.value)" onclick="event.stopPropagation()" style="width:100%;padding:8px;border:1px solid #ddd;border-radius:6px;font-size:13px;resize:vertical;min-height:60px;">${data.comment || ''}</textarea>
                            <div style="display:flex;justify-content:space-between;align-items:center;margin-top:6px;">
                                <label style="display:flex;align-items:center;gap:4px;font-size:11px;color:#666;cursor:pointer;">
                                    <input type="checkbox" ${data.isCommentPublic ? 'checked' : ''} onchange="window.scTogglePublic('${safeId}', this.checked)" onclick="event.stopPropagation()">
                                    <span>Hacer pública</span>
                                </label>
                                <button onclick="event.stopPropagation(); window.scSaveNote('${safeId}', this.parentElement.previousElementSibling.value);" style="background:#104547;color:white;border:none;padding:4px 12px;border-radius:4px;font-size:11px;cursor:pointer;">Guardar</button>
                            </div>
                        </div>
                    </div>
                </div>
            `;
        }).join('');
    };

    window.syncComentarioFirestore = async function(id, nombre, texto, isPublic) {
        if (!window.firebaseDb || !window.firebaseAuth?.currentUser) return;
        const { collection, query, where, getDocs, addDoc, deleteDoc, serverTimestamp } = window.firebaseUtils;
        const uid = window.getActiveUid();
    
        const q = query(
            collection(window.firebaseDb, 'comentarios'),
            where('uid', '==', uid),
            where('cafeId', '==', id)
        );
    
        try {
            const snap = await getDocs(q);
            if (isPublic && texto?.trim()) {
                if (snap.empty) {
                    await addDoc(collection(window.firebaseDb, 'comentarios'), {
                        uid,
                        username: window.getActiveUsername(),
                        cafeId: id,
                        cafe: nombre,
                        texto: texto.trim(),
                        fecha: serverTimestamp()
                    });
                } else {
                    const { updateDoc } = window.firebaseUtils;
                    await updateDoc(snap.docs[0].ref, {
                        texto: texto.trim(),
                        username: window.getActiveUsername()
                    });
                }
            } else {
                snap.forEach(async (d) => {
                    const { deleteDoc } = window.firebaseUtils;
                    await deleteDoc(d.ref);
                });
            }
        } catch (err) {
            console.warn('Firestore comentario error:', err);
        }
    };

    window.scSaveNote = function(id, note) {
        const data = window.getCafeData(id);
        window.saveCafeData(id, { comment: note });
        window.showToast('✓ Nota guardada');
        window.syncComentarioFirestore(id, data.nombre, note, data.isCommentPublic);
    
        if (window.firebaseDb && window.firebaseAuth?.currentUser) {
            const { doc, setDoc } = window.firebaseUtils;
            const uid = window.getActiveUid();
            setDoc(doc(window.firebaseDb, 'users', uid, 'cafes', id),
                { comment: note },
                { merge: true }
            ).catch(err => console.warn('Firestore note error:', err));
        }
    
        const card = document.querySelector(`[data-id="${id}"]`);
        if (card) {
            const badge = card.querySelector('.sc-name');
            const hasNote = note?.trim().length > 0;
            const existing = badge.querySelector('[title="Tiene nota"]');
            if (hasNote && !existing) badge.innerHTML += '<span style="color:#104547;font-size:12px;margin-left:4px" title="Tiene nota">📝</span>';
            else if (!hasNote && existing) existing.remove();
        }
    };
    
    window.scTogglePublic = function(id, isPublic) {
        const data = window.getCafeData(id);  // ← primero leer
        window.saveCafeData(id, { isCommentPublic: isPublic });
        window.syncComentarioFirestore(id, data.nombre, data.comment, isPublic);
    };
    
    window.scRemove = function(id) {
        const userData = window.userCafeData;
        const eraVisitado = userData[id]?.isVisited;
        const eraFavorito = userData[id]?.isFavorite;
    
        if (scCurrentFilter === 'fav') {
            if (userData[id]) {
                userData[id].isFavorite = false;
                if (!userData[id].isVisited) delete userData[id];
            }
        } else {
            delete userData[id];
        }
        localStorage.setItem('buscafes_user_data', JSON.stringify(userData));
        window.userCafeData = userData;
    
        if (window.firebaseDb && window.firebaseAuth?.currentUser && (eraVisitado || eraFavorito)) {
            const { doc, deleteDoc, setDoc, getDoc, increment } = window.firebaseUtils;
            const uid = window.getActiveUid();
    
            // Eliminar el documento del café del usuario
            if (scCurrentFilter === 'fav') {
                // Solo quitar favorito, mantener el doc si era visitado
                setDoc(doc(window.firebaseDb, 'users', uid, 'cafes', id),
                    { isFavorite: false },
                    { merge: true }
                ).catch(err => console.warn('Firestore scRemove fav error:', err));
            } else {
                // Eliminar completamente
                deleteDoc(doc(window.firebaseDb, 'users', uid, 'cafes', id))
                    .catch(err => console.warn('Firestore deleteDoc error:', err));
            }
    
            // Decrementar visitCount del usuario
            const userRef = doc(window.firebaseDb, 'users', uid);
            getDoc(userRef).then(snap => {
                const currentCount = snap.data()?.visitCount || 0;
                if (currentCount > 0) {
                    setDoc(userRef, {
                        username: window.getActiveUsername(),
                        visitCount: increment(-1)
                    }, { merge: true }).catch(err => console.warn('Firestore visitCount error:', err));
                }
            });
        }
    
        window.abrirPanelGuardados();
    };
    
    // Observer para el panel de guardados
    (function iniciarObserver() {
        const panel = document.getElementById('panel-guardados');
        if (!panel) return setTimeout(iniciarObserver, 300);
        
        const observer = new MutationObserver(function(mutations) {
            mutations.forEach(function(m) {
                if (m.attributeName === 'style' && panel.style.display !== 'none') {
                    
                    // Mostrar warning solo si no está logueado
                    const warning = document.getElementById('guest-warning');
                    if (warning) {
                        const isLoggedIn = window.firebaseAuth?.currentUser || 
                                           localStorage.getItem('buscafes_user_email');
                        warning.style.display = isLoggedIn ? 'none' : 'block';
                    }

                    // Inicializar búsqueda (solo la primera vez)
                    const searchEl = document.getElementById('sc-search');
                    if (searchEl && !searchEl._ready) {
                        searchEl.addEventListener('input', function() { 
                            window.abrirPanelGuardados(this.value); 
                        });
                        searchEl._ready = true;
                    }

                    // Inicializar tabs (solo la primera vez)
                    if (!window._scTabsReady) {
                        document.getElementById('sc-tab-all')?.addEventListener('click', function() {
                            scCurrentFilter = 'all';
                            document.querySelectorAll('.sc-tab').forEach(t => t.classList.remove('active'));
                            this.classList.add('active');
                            document.getElementById('sc-search').value = '';
                            window.abrirPanelGuardados();
                        });
                        document.getElementById('sc-tab-fav')?.addEventListener('click', function() {
                            scCurrentFilter = 'fav';
                            document.querySelectorAll('.sc-tab').forEach(t => t.classList.remove('active'));
                            this.classList.add('active');
                            document.getElementById('sc-search').value = '';
                            window.abrirPanelGuardados();
                        });
                        window._scTabsReady = true;
                    }

                    window.abrirPanelGuardados();
                }
            });
        });
        observer.observe(panel, { attributes: true, attributeFilter: ['style'] });
    })();
  </script>
  
</body>
</html>
"""


# Reemplaza el placeholder por tu connection string sin romper las llaves de Dash/JS
app.index_string = app.index_string.replace("__AI_CONN__", CLIENT_CONN)
app.index_string = app.index_string.replace("__GEO_LOOKUP__", json.dumps(geo_lookup, ensure_ascii=False))
app.index_string = app.index_string.replace("__FIREBASE_CONFIG__", FIREBASE_CONFIG_JSON)

# Calcular latitud y longitud mín/máx desde el GeoJSON
latitudes = [feature['geometry']['coordinates'][1] for feature in geojson_data['features']]
longitudes = [feature['geometry']['coordinates'][0] for feature in geojson_data['features']]

lat_min, lat_max = min(latitudes), max(latitudes)
lon_min, lon_max = min(longitudes), max(longitudes)

with open('assets/cafeinit.svg', 'r') as file:
    svg_content = file.read()

# Obtener valores mínimos y máximos de latitud/longitud
lat_min = min(feature['geometry']['coordinates'][1] for feature in geojson_data['features'])
lat_max = max(feature['geometry']['coordinates'][1] for feature in geojson_data['features'])
lon_min = min(feature['geometry']['coordinates'][0] for feature in geojson_data['features'])
lon_max = max(feature['geometry']['coordinates'][0] for feature in geojson_data['features'])

# Obtener valores únicos para dropdowns
barrios_unicos = sorted(set(feature['properties'].get('Barrio', 'Desconocido') for feature in geojson_data['features']))
nombres_unicos = sorted(set(feature['properties'].get('Nombre', 'Desconocido') for feature in geojson_data['features']))

# Obtener valores mínimo y máximo de rating (evita errores con `.get()` y valores por defecto)
ratings = [feature['properties'].get('Rating', 0) for feature in geojson_data['features']]
rating_min = 0
rating_max = 5

def _sort_key(s):
    if not isinstance(s, str):
        return ""
    # quita acentos y pasa a minúsculas
    s_norm = unicodedata.normalize("NFD", s)
    s_norm = "".join(ch for ch in s_norm if unicodedata.category(ch) != "Mn")
    return s_norm.casefold()

barrios_unicos = sorted(
    {f['properties'].get('Barrio', 'Desconocido').strip()
     for f in geojson_data['features']},
    key=_sort_key
)


app.layout = html.Div([
    dcc.Store(id='initial-load', data=True),
    dcc.Store(id='clientside-store-data', data=None),
    dcc.Store(id='info-visible', data=False),

    html.Button("", id="btn-abrir-panel", style={'display': 'none'}, n_clicks=0),
    html.Button("", id="btn-abrir-guardados", style={'display': 'none'}, n_clicks=0),
    html.Button("", id="btn-login", style={'display': 'none'}, n_clicks=0),

    # Panel sugerencias
    html.Div([
        html.Div([
            html.Div([
                html.H3("Informar problema", className="sg-title"),
                html.Button("✕", id="btn-cerrar-panel", className="sg-close-btn"),
            ], className="sg-header"),
            html.Div([
                dcc.Dropdown(
                    id="tipo-sugerencia",
                    options=[
                        {'label': 'Cafetería faltante', 'value': 'cafeteria_faltante'},
                        {'label': 'Cafetería cerrada', 'value': 'cafeteria_cerrada'},
                        {'label': 'Dirección incorrecta', 'value': 'direccion_incorrecta'},
                        {'label': 'Sitio web incorrecto o faltante', 'value': 'sitio_web'},
                        {'label': 'Otro error', 'value': 'otro'},
                    ],
                    value=None,
                    placeholder="¿Qué querés informar? *",
                    searchable=False,
                    clearable=False,
                    className='custom-dropdown',
                    style={'marginBottom': '8px', 'fontSize': '0.9em'}
                ),
                dcc.Input(
                    id="nombre-cafeteria",
                    type="text",
                    placeholder="Nombre de la cafetería *",
                    className="sg-input"
                ),
                dcc.Input(
                    id="direccion-cafeteria",
                    type="text",
                    placeholder="Dirección",
                    className="sg-input"
                ),
                dcc.Input(
                    id="url-cafeteria",
                    type="text",
                    placeholder="URL o Instagram (opcional)",
                    className="sg-input",
                    style={'display': 'none'}
                ),
                dcc.Textarea(
                    id="descripcion-sugerencia",
                    placeholder="Descripción adicional (opcional)",
                    className="sg-input",
                    style={'minHeight': '60px', 'resize': 'vertical', 'display': 'none'}
                ),
                html.Button("Enviar", id="enviar-sugerencia", className="sg-submit-btn"),
                html.Div(id="mensaje-confirmacion", className="sg-message")
            ], className="sg-body")
        ], className="sg-panel"),
    ], id="panel-sugerencia", style={"display": "none"}),

    # Panel guardados
    html.Div([
        html.Div([
            html.Div([
                html.H3("CAFETERIAS VISITADAS", className="sc-panel-title"),
                html.Button("✕", id="btn-cerrar-guardados", className="sc-close-btn", n_clicks=0),
            ], className="sc-panel-header"),

            html.Div([
                html.Span("💾 ", style={'fontSize': '16px'}),
                "Estás en modo anónimo. Tus datos se guardan solo en este dispositivo.",
                html.Br(),
                html.A("Crear cuenta gratuita", href="#", id="link-login-from-guest",
                       style={'color': '#104547', 'fontWeight': '600', 'fontSize': '12px', 'textDecoration': 'underline'})
            ], id="guest-warning", className="guest-warning", style={'display': 'none'}),

            html.Div([
                html.Button("Visitadas", id="sc-tab-all", className="sc-tab active"),
                html.Button("Favoritas", id="sc-tab-fav", className="sc-tab"),
            ], className="sc-tabs"),

            html.Div(
                dcc.Input(
                    id="sc-search",
                    type="text",
                    placeholder="🔍 Buscar en mi lista...",
                    className="sc-search-input",
                    debounce=False
                ),
                className="sc-search-wrapper"
            ),
            html.Div(id='saved-list-container', className="sc-list-wrapper")
        ], className="sc-panel")
    ], id="panel-guardados", style={"display": "none"}),

    # Modal de Login
    html.Div([
        html.Div([
            html.Button("✕", id="btn-cerrar-login", className="login-close-btn"),
            html.Div([
                html.H2("Bienvenido a Buscafes", className="login-title"),
                html.P("Guardá tus cafeterías favoritas en todos tus dispositivos", className="login-subtitle"),

                html.Button([
                    html.Img(src="https://www.gstatic.com/firebasejs/ui/2.0.0/images/auth/google.svg",
                             style={'width': '18px', 'marginRight': '10px'}),
                    "Continuar con Google"
                ], id="btn-google-login", className="login-btn login-btn-google"),

                html.Div("o", className="login-divider"),

                html.Div([
                    dcc.Input(id="login-email", type="email", placeholder="Email", className="login-input"),
                    dcc.Input(id="login-password", type="password", placeholder="Contraseña", className="login-input"),
                    html.Button("Iniciar sesión", id="btn-email-login", className="login-btn login-btn-email"),
                    html.P([
                        "¿No tenés cuenta? ",
                        html.A("Crear cuenta", id="link-signup", className="login-link")
                    ], className="login-footer"),
                ], id="login-form"),

                html.Div([
                    dcc.Input(id="signup-name", type="text", placeholder="Nombre de usuario", className="login-input"),
                    dcc.Input(id="signup-email", type="email", placeholder="Email", className="login-input"),
                    dcc.Input(id="signup-password", type="password", placeholder="Contraseña", className="login-input"),
                    html.Button("Crear cuenta", id="btn-email-signup", className="login-btn login-btn-email"),
                    html.P([
                        "¿Ya tenés cuenta? ",
                        html.A("Iniciar sesión", id="link-login", className="login-link")
                    ], className="login-footer"),
                ], id="signup-form", style={"display": "none"}),

                html.Div(id="login-error", className="login-error")
            ], className="login-content")
        ], className="login-modal")
    ], id="login-overlay", className="login-overlay", style={"display": "none"}),

    # Dropdown de perfil
    html.Div([
        html.Div([
            html.Div(id="profile-user-email", className="profile-email"),
            html.Hr(style={'margin': '8px 0', 'border': 'none', 'borderTop': '1px solid #eee'}),
            html.Button("Cerrar sesión", id="btn-logout", className="profile-logout-btn"),
        ], className="profile-dropdown")
    ], id="profile-dropdown-container", style={"display": "none"}),

    # User menu
    html.Div([
        html.Div([
            html.Div([
                html.Span("", id="user-menu-nombre", style={'fontSize': '15px', 'fontWeight': '700', 'color': '#dac69a'}),
                html.Button("✕",
                    id="btn-cerrar-user-menu",
                    style={
                        'position': 'absolute', 'right': '10px', 'top': '50%', 'transform': 'translateY(-50%)',
                        'background': 'rgba(255,255,255,0.12)', 'border': 'none', 'color': '#fffff5',
                        'fontSize': '14px', 'cursor': 'pointer', 'width': '28px', 'height': '28px',
                        'borderRadius': '50%', 'display': 'flex', 'alignItems': 'center', 'justifyContent': 'center'
                    })
            ], style={
                'background': '#104547', 'padding': '14px 42px 14px 16px', 'position': 'relative',
                'display': 'flex', 'alignItems': 'center', 'justifyContent': 'center'
            }),
            html.Div([
                html.A([
                    html.Img(src="/assets/icon_usuario.png",
                             style={'width': '18px', 'height': '18px', 'marginRight': '8px', 'verticalAlign': 'middle'}),
                    "Mi perfil"
                ], href="/perfil", className="menu-item"),
                html.A([
                    html.Img(src="/assets/icono_comunidad.png",
                             style={'width': '18px', 'height': '18px', 'marginRight': '8px', 'verticalAlign': 'middle'}),
                    "Ver comunidad"
                ], href="/comunidad", className="menu-item"),
                html.Hr(style={'margin': '4px 0', 'border': 'none', 'borderTop': '1px solid #eee'}),
                html.Div("🔑  Logearme", id="menu-auth-action", className="menu-item menu-item-primary"),
                html.Hr(style={'margin': '4px 0', 'border': 'none', 'borderTop': '1px solid #eee'}),
                html.Div([
                    html.A("Privacidad", href="/privacidad", target="_blank",
                           style={'color': '#999', 'fontSize': '11px', 'textDecoration': 'none'}),
                    html.Span(" · ", style={'color': '#999', 'fontSize': '11px'}),
                    html.A("Términos", href="/terminos", target="_blank",
                           style={'color': '#999', 'fontSize': '11px', 'textDecoration': 'none'}),
                ], style={'padding': '8px 16px'}),
            ], style={'padding': '0px 0'})
        ], className="user-menu-content")
    ], id="user-menu", className="user-menu", style={"display": "none"}),
    html.Div([
        html.Div([
            html.Div(style={
                'width': '50px',
                'height': '50px',
                'border': '4px solid #e0e0e0',
                'borderTop': '4px solid #104547',
                'borderRadius': '50%',
                'animation': 'spin 1s linear infinite'
            }),
            html.P("Estamos preparando el café ☕", style={
                'marginTop': '16px',
                'fontFamily': 'Montserrat, sans-serif',
                'fontSize': '14px',
                'fontWeight': '600',
                'color': '#104547',
                'textAlign': 'center'
            })
        ], style={'display': 'flex', 'flexDirection': 'column', 'alignItems': 'center'})
    ], id='loading-div', style={
        'position': 'fixed',
        'top': '0',
        'left': '0',
        'width': '100%',
        'height': '100%',
        'display': 'flex',
        'justifyContent': 'center',
        'alignItems': 'center',
        'backgroundColor': 'rgba(255, 255, 255, 1)',
        'zIndex': '3000'
    }),

    # Panel de filtros
    html.Div(
        id='filters-panel',
        className='controls-container hidden',
        children=[
            html.Div([
                html.H3("Filtros", style={'margin': 0}),
                html.Button("✕", id="btn-cerrar-filtros", className="filters-close-btn"),
            ], className="filters-header"),

            html.Div([
                dcc.Dropdown(
                    id='barrio-dropdown',
                    options=[{'label': b, 'value': b} for b in barrios_unicos],
                    value=None,
                    placeholder="Selecciona un barrio",
                    className='custom-dropdown',
                    labels={'select_all': '', 'deselect_all': ''},
                    searchable=False,
                    multi=True
                ),

                dcc.Dropdown(
                    id='feature-filter',
                    options=[
                        {'label': 'Tiene pasteleria casera', 'value': 'Tiene pastelería artesanal'},
                        {'label': 'El café es de especialidad', 'value': 'El café es de especialidad'},
                        {'label': 'Tiene Delivery', 'value': 'Delivery'},
                        {'label': 'Tiene takeaway', 'value': 'Tiene takeaway'},
                        {'label': 'Es nueva', 'value': 'Nueva'},
                        {'label': 'Es popular', 'value': 'Popular'},
                        {'label': 'Temática: Puesto de diario', 'value': 'Temática: Puesto de diario'},
                        {'label': 'Brunch', 'value': 'Sirve brunch'},
                        {'label': 'Con espacio afuera', 'value': 'Espacio afuera'},
                        {'label': 'Es cadena', 'value': 'Es cadena'},
                        {'label': 'No es cadena', 'value': 'No es cadena'},
                        {'label': 'Musica en vivo', 'value': 'Musica en vivo'},
                        {'label': 'Reservable', 'value': 'Reservable'},
                        {'label': 'Tiene comida vegeteriana', 'value': 'Tiene comida vegetariana'},
                        {'label': 'Permite mascotas', 'value': 'Permite mascotas'},
                        {'label': 'Acceso silla de ruedas', 'value': 'Acceso silla de ruedas'},
                        {'label': 'Tiene opciones sin tacc', 'value': 'Tiene opciones sin tacc'}
                    ],
                    value=[],
                    searchable=False,
                    multi=True,
                    labels={'select_all': '', 'deselect_all': ''},
                    placeholder="Filtrá por Características...",
                    className='custom-dropdown'
                ),

                dcc.Dropdown(
                    id='dias-apertura-filter',
                    options=[{'label': day, 'value': day} for day in
                             ['Domingo', 'Lunes', 'Martes', 'Miercoles', 'Jueves', 'Viernes', 'Sabado']],
                    value=[],
                    multi=True,
                    labels={'select_all': '', 'deselect_all': ''},
                    searchable=False,
                    placeholder="Filtrá por Días de Apertura...",
                    className='custom-dropdown'
                ),

                dcc.Dropdown(
                    id='nombre-filter',
                    options=[],
                    value=[],
                    multi=True,
                    labels={'select_all': '', 'deselect_all': ''},
                    placeholder="Busca por Nombre...",
                    searchable=True,
                    className='custom-dropdown',
                    style={'boxShadow': '0px 0px 5px 2px rgba(0, 0, 0, 0.1)', 'marginTop': '2px'}
                ),

                html.Label(
                    "RATING",
                    style={
                        'display': 'block',
                        'color': '#333',
                        'fontWeight': 'bold',
                        'marginBottom': '10px',
                        'marginLeft': '40px',
                        'marginTop': '15px'
                    }
                ),

                dcc.RangeSlider(
                    id='rating-slider',
                    min=rating_min,
                    max=rating_max,
                    step=0.1,
                    marks={
                        rating: {
                            'label': str(rating),
                            'style': {'color': '#333'}
                        }
                        for rating in range(int(rating_min), int(rating_max) + 1)
                    },
                    value=[rating_min, rating_max],
                    tooltip={
                        "placement": "bottom",
                        "always_visible": False,
                        "style": {"color": "#104547", "fontSize": "12px"}
                    },
                    className='custom-slider',
                    allow_direct_input=False
                ),

                dcc.Dropdown(
                    id='map-style-dropdown',
                    options=[
                        {'label': 'Mapa tradicional', 'value': 'osm'},
                        {'label': 'Modo Claro', 'value': 'carto-positron'},
                        {'label': 'Modo Oscuro', 'value': 'carto-darkmatter'}
                    ],
                    value='carto-positron',
                    placeholder="Estilo de mapa",
                    searchable=False,
                    className='custom-dropdown',
                    style={'marginTop': '15px'}
                ),
            ], className="filters-body"),
        ]
    ),

    # Mapa
    dl.Map(
        id='map',
        style={'width': '100%', 'height': '100vh'},
        center=[-34.598, -58.436],
        zoomControl=False,
        bounds=[[lat_min, lon_min], [lat_max, lon_max]],
        zoom=12,
        children=[
            dl.TileLayer(
                id="base-layer",
                url="https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png",
                detectRetina=False
            ),
            dl.LocateControl(locateOptions={'enableHighAccuracy': True, 'setView': 'once'},
                             position='topright', showPopup=False),
            dl.ZoomControl(position='topright'),
            dl.GeoJSON(
                id="geojson-layer",
                data={'type': 'FeatureCollection', 'features': []},
                options=dict(
                    pointToLayer=assign("""
                        function(feature, latlng){
                            const props = feature.properties;
                            let iconUrl = props.iconUrl;
                            
                            let marker = L.marker(latlng, {
                                icon: L.icon({
                                    iconUrl: iconUrl,
                                    iconSize: [18, 27],
                                    iconAnchor: [12, 23],
                                    popupAnchor: [1, -34],
                                    shadowSize: [0, 0]
                                })
                            });
                            
                            const tooltipHTML = `
                                <p class='nombre'>${props.Nombre}</p>
                                <p><span class='bold-text'>Rating: </span>${props.Rating}</p>
                                <p><span class='bold-text'>Dirección: </span>${props['Dirección']}</p>
                            `;
                            marker.bindTooltip(tooltipHTML, {className: 'marker-tooltip'});
                    
                            marker.on('click', function(){
                                const days = ['Domingo', 'Lunes', 'Martes', 'Miercoles', 'Jueves', 'Viernes', 'Sabado'];
                                let horariosHTML = '<strong style="text-decoration: underline;">Horarios:</strong><br>';
                                
                                days.forEach(day => {
                                    const open = props[day + '_open'];
                                    const close = props[day + '_close'];
                                    if (open && close && open !== 'None' && close !== 'None') {
                                        horariosHTML += day + ': ' + open + ' - ' + close + '<br>';
                                    } else {
                                        horariosHTML += day + ': No abre<br>';
                                    }
                                });

                                                                
                                const sitioWebRaw = props['Sitio Web'] || '';
                                const sitioWeb = sitioWebRaw && sitioWebRaw !== 'Sin datos' 
                                    ? `<a href="${sitioWebRaw}" target="_blank" style="color:#104547;">${sitioWebRaw.replace(/^https?:\/\//, '').replace(/\/$/, '')}</a>`
                                    : 'Sin datos';
                    
                                const id = props.id;
                                const nombre = props.Nombre;
                                const safeNombre = nombre.replace(/'/g, "\\\\'");
                                const cafeData = window.getCafeData(id);
                                const esFav = cafeData.isFavorite === true;
                                const esVist = cafeData.isVisited === true;
                                const hasNote = cafeData.comment && cafeData.comment.trim();
                                const popupHTML = `
                                    <p class='popup-nombre'><strong>${nombre}</strong></p>
                                    <p class='popup-rating'><strong>Rating:</strong> ${props.Rating}</p>
                                    <p class='popup-reviews'><strong>Reviews:</strong> ${props['Cantidad Reviews']}</p>
                                    <p class='popup-web'><strong>Sitio Web:</strong> ${sitioWeb}</p>
                                    <p class='popup-direccion'><strong>Dirección:</strong> ${props['Dirección']}</p>
                                    <p class='popup-horarios'>${horariosHTML}</p>
                                    <div class='popup-actions'>
                                        <button 
                                            id='btn-fav-${id}' 
                                            class='popup-action-btn ${esFav ? "active" : ""}' 
                                            onclick='window.toggleFavorito("${id}")'>
                                            ${esFav ? '❤️' : '🤍'} Favorito
                                        </button>
                                        <button 
                                            id='btn-vist-${id}' 
                                            class='popup-action-btn ${esVist ? "active" : ""}' 
                                            onclick='window.toggleVisitado("${id}")'>
                                            ${esVist ? '✅' : '📍'} Visitado
                                        </button>
                                        <button 
                                            class='popup-action-btn ${hasNote ? "active" : ""}' 
                                            onclick='window.openNoteModal("${id}")'>
                                            📝 ${hasNote ? 'Ver nota' : 'Nota'}
                                        </button>
                                    </div>
                                `;
                                
                                var popup = L.popup({closeOnMove: false})
                                    .setLatLng(latlng)
                                    .setContent(popupHTML)
                                    .openOn(marker._map);
                    
                                var zoomLevel = marker._map.getZoom();
                                var latOffset = 0.05 / Math.pow(2, zoomLevel - 12);
                                marker._map.panTo([latlng.lat + latOffset, latlng.lng], {animate: true});
                            });
                            
                            return marker;
                        }
                    """)
                ),
                zoomToBoundsOnClick=True,
            )
        ]
    ),

    # Mensaje de zoom
    html.Div([
        "Haz zoom para ver más cafeterías",
        html.Button('✖', id='close-message-button', style={
            'background': 'none',
            'border': 'none',
            'color': 'black',
            'fontSize': '10px',
            'cursor': 'pointer',
            'position': 'absolute',
            'right': '1px',
            'top': '1px'
        })
    ],
        id='zoom-message',
        style={
            'position': 'fixed',
            'bottom': '80px',
            'left': '50%',
            'transform': 'translateX(-50%)',
            'backgroundColor': '#d3d3d3',
            'color': 'black',
            'padding': '10px 20px',
            'borderRadius': '8px',
            'boxShadow': '0px 4px 10px rgba(0, 0, 0, 0.1)',
            'fontWeight': 'bold',
            'zIndex': '2000',
            'fontSize': '14px',
            'textAlign': 'center',
            'width': 'auto',
            'maxWidth': '80%'
        }
    ),
])

@app.callback(
    [Output("url-cafeteria", "style"),
     Output("descripcion-sugerencia", "style"),
     Output("nombre-cafeteria", "placeholder"),
     Output("direccion-cafeteria", "placeholder"),
     Output("url-cafeteria", "placeholder"),
     Output("descripcion-sugerencia", "placeholder")],
    Input("tipo-sugerencia", "value"),
    prevent_initial_call=True
)
def actualizar_campos_sugerencia(tipo):
    url_style = {'display': 'none'}
    desc_style = {'minHeight': '60px', 'resize': 'vertical', 'display': 'none'}
    nombre_ph = "Nombre de la cafetería *"
    dir_ph = "Dirección (opcional)"
    url_ph = "URL o Instagram (opcional)"
    desc_ph = "Descripción adicional (opcional)"

    if tipo == 'cafeteria_faltante':
        url_style = {'display': 'block', 'marginBottom': '8px', 'width': '100%', 'boxSizing': 'border-box'}
        dir_ph = "Dirección *"
        desc_style = {'minHeight': '60px', 'resize': 'vertical', 'display': 'block',
                      'marginBottom': '8px', 'width': '100%', 'boxSizing': 'border-box'}

    elif tipo == 'cafeteria_cerrada':
        dir_ph = "Dirección (opcional)"
        desc_style = {'minHeight': '60px', 'resize': 'vertical', 'display': 'block',
                      'marginBottom': '8px', 'width': '100%', 'boxSizing': 'border-box'}

    elif tipo == 'direccion_incorrecta':
        dir_ph = "Dirección incorrecta *"
        desc_style = {'minHeight': '60px', 'resize': 'vertical', 'display': 'block',
                      'marginBottom': '8px', 'width': '100%', 'boxSizing': 'border-box'}
        desc_ph = "Dirección correcta o comentario (opcional)"

    elif tipo == 'sitio_web':
        url_style = {'display': 'block', 'marginBottom': '8px', 'width': '100%', 'boxSizing': 'border-box'}
        url_ph = "URL o Instagram del sitio correcto (opcional)"
        desc_style = {'minHeight': '60px', 'resize': 'vertical', 'display': 'block',
                      'marginBottom': '8px', 'width': '100%', 'boxSizing': 'border-box'}

    elif tipo == 'otro':
        nombre_ph = "Nombre de la cafetería (opcional)"
        dir_ph = "Dirección (opcional)"
        desc_style = {'minHeight': '60px', 'resize': 'vertical', 'display': 'block',
                      'marginBottom': '8px', 'width': '100%', 'boxSizing': 'border-box'}
        desc_ph = "Describí el problema *"

    return url_style, desc_style, nombre_ph, dir_ph, url_ph, desc_ph

@app.callback(
    Output('loading-div', 'style'),
    Input('geojson-layer', 'data'),
    Input('clientside-store-data', 'data'),  # ← trigger alternativo
    prevent_initial_call=True
)
def hide_spinner_on_load(geojson_data, store_data):
    # Ocultar si llegó cualquiera de los dos
    if geojson_data or store_data:
        return {'display': 'none'}
    return {
        'position': 'fixed', 'top': '0', 'left': '0',
        'width': '100%', 'height': '100%', 'display': 'flex',
        'justify-content': 'center', 'align-items': 'center',
        'background-color': 'rgba(255,255,255,0.8)', 'z-index': '2000'
    }



# Configuración de Azure Blob Storage
BLOB_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
BLOB_CONTAINER = "contbuscafe"  # Contenedor en tu cuenta de almacenamiento
BLOB_FILENAME = "sugerencias.json"  # Archivo donde se guardarán las sugerencias


@app.callback(
    Output("panel-guardados", "style"),
    Input("btn-abrir-guardados", "n_clicks"),
    State("panel-guardados", "style"),
    prevent_initial_call=True
)
def toggle_panel_guardados(n_abrir, current_style):
    if n_abrir:
        return {"display": "block"}
    return current_style



# Callback para guardar la sugerencia en Azure Blob Storage
@app.callback(
    Output("mensaje-confirmacion", "children"),
    Input("enviar-sugerencia", "n_clicks"),
    State("tipo-sugerencia", "value"),
    State("nombre-cafeteria", "value"),
    State("direccion-cafeteria", "value"),
    State("url-cafeteria", "value"),
    State("descripcion-sugerencia", "value"),
    prevent_initial_call=True
)
def guardar_sugerencia(n_clicks, tipo, nombre, direccion, url, descripcion):
    if not tipo:
        return "❌ Seleccioná el tipo de problema."
    if tipo != 'otro' and not nombre:
        return "❌ El nombre de la cafetería es obligatorio."
    if tipo in ['cafeteria_faltante', 'direccion_incorrecta'] and not direccion:
        return "❌ La dirección es obligatoria para este tipo de reporte."

    tipos_label = {
        'cafeteria_faltante': 'Cafetería faltante',
        'cafeteria_cerrada': 'Cafetería cerrada',
        'direccion_incorrecta': 'Dirección incorrecta',
        'sitio_web': 'Sitio web incorrecto o faltante',
        'otro': 'Otro error'
    }

    sugerencia = {
        'tipo': tipos_label.get(tipo, tipo),
        'nombre': nombre or '',
        'direccion': direccion or '',
        'url': url or '',
        'descripcion': descripcion or '',
        'timestamp': datetime.now().isoformat()
    }

    try:
        if not BLOB_CONNECTION_STRING:
            return "❌ Error de configuración del servidor."
        blob_service_client = BlobServiceClient.from_connection_string(BLOB_CONNECTION_STRING)
        filename = f"sugerencia_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        blob_client = blob_service_client.get_blob_client(container=BLOB_CONTAINER, blob=filename)
        blob_client.upload_blob(json.dumps(sugerencia, indent=2, ensure_ascii=False), overwrite=True)
        return "✅ ¡Gracias! Tu reporte fue enviado."
    except Exception as e:
        return f"❌ Error al enviar: {str(e)}"

app.clientside_callback(
    """
    async function(_ignored) {
        const res  = await fetch('/api/geojson');
        const data = await res.json();
        return data;
    }
    """,
    Output('clientside-store-data', 'data'),
    Input('initial-load', 'data'),   # ya tenés este Store en el layout
)

app.clientside_callback(
    """
        function(barrios, features, rating, dias, nombre, bounds, zoom, store) {
    
        if (!store || !store.features) {
            return window.dash_clientside.no_update;
        }
    
        const ctx = dash_clientside.callback_context;
        const triggered = ctx.triggered[0]?.prop_id;
    
        let feats = store.features;
    
        // filtros comunes
        if (barrios?.length) {
            feats = feats.filter(f => barrios.includes(f.properties.Barrio));
        }
        if (features?.length) {
            feats = feats.filter(f => features.every(ff => f.properties[ff] === true));
        }
        if (rating?.length === 2) {
            feats = feats.filter(f =>
                f.properties.Rating >= rating[0] &&
                f.properties.Rating <= rating[1]
            );
        }
        if (dias?.length) {
            feats = feats.filter(f =>
                dias.every(d => f.properties[d + '_open'] && f.properties[d + '_close'])
            );
        }
    
        // 🔒 CASO NOMBRE: PRIORIDAD ABSOLUTA
        if (nombre?.length) {
            return {
                type: 'FeatureCollection',
                features: feats.filter(f => nombre.includes(f.properties.Nombre))
            };
        }
    
        // recién acá aplicar zoom / bounds
        if (zoom < 14) {
            const reviews = feats
                .map(f => f.properties['Cantidad Reviews'] || 0)
                .sort((a,b)=>b-a);
            const t = reviews[Math.floor(reviews.length * 0.07)] || 0;
            return {
                type:'FeatureCollection',
                features: feats.filter(f => f.properties['Cantidad Reviews'] >= t)
            };
        }
    
        if (bounds?.length === 2) {
            const [sw, ne] = bounds;
            feats = feats.filter(f => {
                const [lng, lat] = f.geometry.coordinates;
                return lat>=sw[0] && lat<=ne[0] && lng>=sw[1] && lng<=ne[1];
            });
        }
    
        return {type:'FeatureCollection', features: feats};
    }
    """,
    Output('geojson-layer','data'),
    [
        Input('barrio-dropdown','value'),
        Input('feature-filter','value'),
        Input('rating-slider','value'),
        Input('dias-apertura-filter','value'),
        Input('nombre-filter','value'),
        Input('map','bounds'),
        Input('map','zoom'),
        Input('clientside-store-data','data'),
    ]
    
)



@app.callback(
    Output('nombre-filter', 'options'),
    Input('nombre-filter', 'search_value'),
    State('nombre-filter', 'value')  # 👈 Agregamos el estado actual
)
def update_nombre_options(search_value, current_value):
    # Si hay valores seleccionados, mantener esas opciones visibles
    if current_value:
        selected_options = [{'label': n, 'value': n} for n in (current_value if isinstance(current_value, list) else [current_value])]
        
        # Si no hay búsqueda, solo mostrar los seleccionados
        if not search_value or len(search_value) < 2:
            return selected_options
        
        # Si hay búsqueda, combinar seleccionados + resultados
        s = search_value.lower()
        results = [n for n in nombres_unicos if s in n.lower() and n not in (current_value if isinstance(current_value, list) else [current_value])]
        return selected_options + [{'label': n, 'value': n} for n in results[:50]]
    
    # Comportamiento original cuando no hay nada seleccionado
    if not search_value or len(search_value) < 2:
        return []
    
    s = search_value.lower()
    results = [n for n in nombres_unicos if s in n.lower()]
    return [{'label': n, 'value': n} for n in results[:50]]


@app.callback(
    Output("panel-sugerencia", "style"),
    Input("btn-abrir-panel", "n_clicks"),
    State("panel-sugerencia", "style"),
    prevent_initial_call=True
)
def toggle_suggestion_panel(n_clicks_abrir, current_style):
    if n_clicks_abrir:
        return {"display": "block"}
    return current_style

#log in button

@app.callback(
    Output("login-overlay", "style"),
    Input("btn-login", "n_clicks"),
    State("login-overlay", "style"),
    prevent_initial_call=True
)
def toggle_login_modal(n_open, current_style):
    if n_open:
        return {"display": "flex"}
    return current_style


@app.callback(
    [Output("login-form", "style"),
     Output("signup-form", "style")],
    [Input("link-signup", "n_clicks"),
     Input("link-login", "n_clicks")],
    prevent_initial_call=True
)
def toggle_login_signup(n_signup, n_login):
    ctx = dash.callback_context
    if not ctx.triggered:
        return {"display": "block"}, {"display": "none"}
    
    triggered_id = ctx.triggered[0]['prop_id'].split('.')[0]
    
    if triggered_id == "link-signup":
        return {"display": "none"}, {"display": "block"}
    else:
        return {"display": "block"}, {"display": "none"}



@app.callback(
    Output('base-layer', 'url'),
    Input('map-style-dropdown', 'value')
)
def update_map_style(map_style):
    style_urls = {
        'osm': 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
        'carto-positron': 'https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png',
        'carto-darkmatter': 'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png'
    }

    # Default
    return style_urls.get(map_style, style_urls['carto-positron'])


  
    
# Ejecuta la aplicación Dash
if __name__ == "__main__":
    app.run_server(debug=False)
