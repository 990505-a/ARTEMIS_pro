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

import { Component, ChangeDetectionStrategy, inject } from '@angular/core';

import { RouterLink, RouterLinkActive } from '@angular/router';

import { TranslatePipe, TranslateService } from '../../core/i18n';

@Component({
  selector: 'app-nav-switcher',
  standalone: true,
  imports: [RouterLink, RouterLinkActive, TranslatePipe],
  template: `
    <nav class="floating-nav-switcher" aria-label="Main Navigation">
      <a 
        routerLink="/" 
        routerLinkActive="active" 
        [routerLinkActiveOptions]="{exact: true}"
        class="nav-tab-btn"
        [title]="'Return to Home Launcher to start a new task' | t"
      >
        <span class="material-symbols-outlined tab-icon">add_task</span>
        <span class="tab-label">{{ 'New / Home' | t }}</span>
      </a>
      <a 
        routerLink="/workspace" 
        routerLinkActive="active" 
        class="nav-tab-btn"
        [title]="'Open Workspace' | t"
      >
        <span class="material-symbols-outlined tab-icon">space_dashboard</span>
        <span class="tab-label">{{ 'Workspace' | t }}</span>
      </a>
      <button
        type="button"
        class="nav-tab-btn lang-toggle-btn"
        (click)="translate.toggleLang()"
        [title]="translate.lang() === 'zh' ? 'Switch to English' : '切换为中文'"
      >
        <span class="material-symbols-outlined tab-icon">translate</span>
        <span class="tab-label">{{ translate.lang() === 'zh' ? 'EN' : '中文' }}</span>
      </button>
    </nav>
  `,
  changeDetection: ChangeDetectionStrategy.Eager,
  styleUrls: ['./nav-switcher.component.scss']
})
export class NavSwitcherComponent {
  protected readonly translate = inject(TranslateService);
}
