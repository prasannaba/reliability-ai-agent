import { ChangeDetectionStrategy, Component, input } from '@angular/core';

/** Material Symbols Outlined icon. Usage: `<app-icon name="settings" />`. */
@Component({
  selector: 'app-icon',
  template: `<span class="material-symbols-outlined" aria-hidden="true">{{ name() }}</span>`,
  styles: [
    `
      :host {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        flex: none;
        line-height: 1;
        font-size: 20px;
      }
      .material-symbols-outlined {
        font-family: 'Material Symbols Outlined';
        font-weight: normal;
        font-style: normal;
        font-size: inherit;
        line-height: 1;
        letter-spacing: normal;
        text-transform: none;
        display: inline-block;
        white-space: nowrap;
        direction: ltr;
        -webkit-font-smoothing: antialiased;
        text-rendering: optimizeLegibility;
        font-feature-settings: 'liga';
        user-select: none;
      }
    `,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class IconComponent {
  readonly name = input.required<string>();
}
