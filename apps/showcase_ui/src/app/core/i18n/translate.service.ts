/**
 * Copyright 2026 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

import { Injectable, signal } from '@angular/core';

import { ZH_TRANSLATIONS } from './zh';

export type Lang = 'en' | 'zh';

const LANG_STORAGE_KEY = 'artemis.ui.lang';

/**
 * Runtime language switcher for the showcase UI.
 *
 * Keys are the exact English source strings from the templates; the English
 * "dictionary" is therefore the identity mapping and only the Chinese table
 * is stored. A missing key falls back to the key itself, so untranslated
 * strings render in English instead of breaking the page.
 */
@Injectable({ providedIn: 'root' })
export class TranslateService {
  private readonly _lang = signal<Lang>(TranslateService.initialLang());

  readonly lang = this._lang.asReadonly();

  setLang(lang: Lang): void {
    this._lang.set(lang);
    try {
      localStorage.setItem(LANG_STORAGE_KEY, lang);
    } catch {
      // Storage unavailable (private mode): keep the in-memory switch.
    }
  }

  toggleLang(): void {
    this.setLang(this._lang() === 'zh' ? 'en' : 'zh');
  }

  t(key: string): string {
    if (this._lang() === 'en') {
      return key;
    }
    return ZH_TRANSLATIONS[key] || key;
  }

  private static initialLang(): Lang {
    try {
      const saved = localStorage.getItem(LANG_STORAGE_KEY);
      if (saved === 'en' || saved === 'zh') {
        return saved;
      }
    } catch {
      // Fall through to browser detection.
    }
    const nav = (navigator as { language?: string }).language ?? '';
    return nav.toLowerCase().startsWith('zh') ? 'zh' : 'en';
  }
}
