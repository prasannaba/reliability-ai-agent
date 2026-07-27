import {
  P,
  d
} from "./chunk-OKX6YYAL.js";
import {
  DomSanitizer
} from "./chunk-ZS2D675J.js";
import {
  HttpClient
} from "./chunk-Z5CKM7C6.js";
import {
  isPlatformBrowser
} from "./chunk-HARQTZKB.js";
import "./chunk-UPWCTHOJ.js";
import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  ElementRef,
  EventEmitter,
  Injectable,
  InjectionToken,
  Input,
  NgModule,
  NgZone,
  Output,
  PLATFORM_ID,
  Pipe,
  RuntimeError,
  SecurityContext,
  Subject,
  ViewContainerRef,
  assertInInjectionContext,
  assertNotInReactiveContext,
  computed,
  distinctUntilChanged,
  first,
  inject,
  map,
  mapTo,
  merge,
  of,
  setClassMetadata,
  shareReplay,
  signal,
  switchMap,
  takeUntil,
  timer,
  ɵɵNgOnChangesFeature,
  ɵɵadvance,
  ɵɵclassProp,
  ɵɵdefineComponent,
  ɵɵdefineInjectable,
  ɵɵdefineInjector,
  ɵɵdefineNgModule,
  ɵɵdefinePipe,
  ɵɵdomElementEnd,
  ɵɵdomElementStart,
  ɵɵdomListener,
  ɵɵprojection,
  ɵɵprojectionDef,
  ɵɵtext,
  ɵɵtextInterpolate
} from "./chunk-CGESL4WZ.js";
import {
  __spreadValues
} from "./chunk-GOMI4DH3.js";

// node_modules/@angular/core/fesm2022/rxjs-interop.mjs
function toSignal(source, options) {
  typeof ngDevMode !== "undefined" && ngDevMode && assertNotInReactiveContext(toSignal, "Invoking `toSignal` causes new subscriptions every time. Consider moving `toSignal` outside of the reactive context and read the signal value where needed.");
  const requiresCleanup = !options?.manualCleanup;
  if (ngDevMode && requiresCleanup && !options?.injector) {
    assertInInjectionContext(toSignal);
  }
  const cleanupRef = requiresCleanup ? options?.injector?.get(DestroyRef) ?? inject(DestroyRef) : null;
  const equal = makeToSignalEqual(options?.equal);
  let state;
  if (options?.requireSync) {
    state = signal({
      kind: 0
    }, __spreadValues({
      equal
    }, ngDevMode ? createDebugNameObject(options?.debugName, "state") : void 0));
  } else {
    state = signal({
      kind: 1,
      value: options?.initialValue
    }, __spreadValues({
      equal
    }, ngDevMode ? createDebugNameObject(options?.debugName, "state") : void 0));
  }
  let destroyUnregisterFn;
  const sub = source.subscribe({
    next: (value) => state.set({
      kind: 1,
      value
    }),
    error: (error) => {
      state.set({
        kind: 2,
        error
      });
      destroyUnregisterFn?.();
    },
    complete: () => {
      destroyUnregisterFn?.();
    }
  });
  if (options?.requireSync && state().kind === 0) {
    throw new RuntimeError(601, (typeof ngDevMode === "undefined" || ngDevMode) && "`toSignal()` called with `requireSync` but `Observable` did not emit synchronously.");
  }
  destroyUnregisterFn = cleanupRef?.onDestroy(sub.unsubscribe.bind(sub));
  return computed(() => {
    const current = state();
    switch (current.kind) {
      case 1:
        return current.value;
      case 2:
        throw current.error;
      case 0:
        throw new RuntimeError(601, (typeof ngDevMode === "undefined" || ngDevMode) && "`toSignal()` called with `requireSync` but `Observable` did not emit synchronously.");
    }
  }, __spreadValues({
    equal: options?.equal
  }, ngDevMode ? createDebugNameObject(options?.debugName, "source") : void 0));
}
function makeToSignalEqual(userEquality = Object.is) {
  return (a, b) => a.kind === 1 && b.kind === 1 && userEquality(a.value, b.value);
}
function createDebugNameObject(toSignalDebugName, internalSignalDebugName) {
  return {
    debugName: `toSignal${toSignalDebugName ? "#" + toSignalDebugName : ""}.${internalSignalDebugName}`
  };
}

// node_modules/ngx-markdown/fesm2022/ngx-markdown.mjs
var _c0 = ["*"];
var BUTTON_TEXT_COPY = "Copy";
var BUTTON_TEXT_COPIED = "Copied";
var ClipboardButtonComponent = class _ClipboardButtonComponent {
  constructor() {
    this._buttonClick$ = new Subject();
    this.copied = toSignal(this._buttonClick$.pipe(switchMap(() => merge(of(true), timer(3e3).pipe(mapTo(false)))), distinctUntilChanged(), shareReplay(1)));
    this.copiedText = computed(() => this.copied() ? BUTTON_TEXT_COPIED : BUTTON_TEXT_COPY, ...ngDevMode ? [{
      debugName: "copiedText"
    }] : []);
  }
  onCopyToClipboardClick() {
    this._buttonClick$.next();
  }
  static {
    this.ɵfac = function ClipboardButtonComponent_Factory(__ngFactoryType__) {
      return new (__ngFactoryType__ || _ClipboardButtonComponent)();
    };
  }
  static {
    this.ɵcmp = ɵɵdefineComponent({
      type: _ClipboardButtonComponent,
      selectors: [["markdown-clipboard"]],
      decls: 2,
      vars: 3,
      consts: [[1, "markdown-clipboard-button", 3, "click"]],
      template: function ClipboardButtonComponent_Template(rf, ctx) {
        if (rf & 1) {
          ɵɵdomElementStart(0, "button", 0);
          ɵɵdomListener("click", function ClipboardButtonComponent_Template_button_click_0_listener() {
            return ctx.onCopyToClipboardClick();
          });
          ɵɵtext(1);
          ɵɵdomElementEnd();
        }
        if (rf & 2) {
          ɵɵclassProp("copied", ctx.copied());
          ɵɵadvance();
          ɵɵtextInterpolate(ctx.copiedText());
        }
      },
      encapsulation: 2,
      changeDetection: 0
    });
  }
};
(() => {
  (typeof ngDevMode === "undefined" || ngDevMode) && setClassMetadata(ClipboardButtonComponent, [{
    type: Component,
    args: [{
      selector: "markdown-clipboard",
      template: `
    <button
      class="markdown-clipboard-button"
      [class.copied]="copied()"
      (click)="onCopyToClipboardClick()"
    >{{ copiedText() }}</button>
  `,
      changeDetection: ChangeDetectionStrategy.OnPush
    }]
  }], null, null);
})();
var CLIPBOARD_OPTIONS = new InjectionToken("CLIPBOARD_OPTIONS");
var KatexSpecificOptions = class {
};
var LanguagePipe = class _LanguagePipe {
  transform(value, language) {
    if (value == null) {
      value = "";
    }
    if (language == null) {
      language = "";
    }
    if (typeof value !== "string") {
      console.error(`LanguagePipe has been invoked with an invalid value type [${typeof value}]`);
      return value;
    }
    if (typeof language !== "string") {
      console.error(`LanguagePipe has been invoked with an invalid parameter [${typeof language}]`);
      return value;
    }
    return "```" + language + "\n" + value + "\n```";
  }
  static {
    this.ɵfac = function LanguagePipe_Factory(__ngFactoryType__) {
      return new (__ngFactoryType__ || _LanguagePipe)();
    };
  }
  static {
    this.ɵpipe = ɵɵdefinePipe({
      name: "language",
      type: _LanguagePipe,
      pure: true
    });
  }
};
(() => {
  (typeof ngDevMode === "undefined" || ngDevMode) && setClassMetadata(LanguagePipe, [{
    type: Pipe,
    args: [{
      name: "language"
    }]
  }], null, null);
})();
var MARKED_EXTENSIONS = new InjectionToken("MARKED_EXTENSIONS");
var MARKED_OPTIONS = new InjectionToken("MARKED_OPTIONS");
var MERMAID_OPTIONS = new InjectionToken("MERMAID_OPTIONS");
var SANITIZE = new InjectionToken("SANITIZE");
function isSanitizeFunction(sanitize) {
  return typeof sanitize === "function";
}
var errorJoyPixelsNotLoaded = "[ngx-markdown] When using the `emoji` attribute you *have to* include Emoji-Toolkit files to `angular.json` or use imports. See README for more information";
var errorKatexNotLoaded = "[ngx-markdown] When using the `katex` attribute you *have to* include KaTeX files to `angular.json` or use imports. See README for more information";
var errorMermaidNotLoaded = "[ngx-markdown] When using the `mermaid` attribute you *have to* include Mermaid files to `angular.json` or use imports. See README for more information";
var errorClipboardNotLoaded = "[ngx-markdown] When using the `clipboard` attribute you *have to* include Clipboard files to `angular.json` or use imports. See README for more information";
var errorClipboardViewContainerRequired = "[ngx-markdown] When using the `clipboard` attribute you *have to* provide the `viewContainerRef` parameter to `MarkdownService.render()` function";
var errorSrcWithoutHttpClient = "[ngx-markdown] When using the `src` attribute you *have to* pass the `HttpClient` as a parameter of the `forRoot` method. See README for more information";
var ExtendedRenderer = class extends P {
  constructor() {
    super(...arguments);
    this.ɵNgxMarkdownRendererExtendedForExtensions = false;
    this.ɵNgxMarkdownRendererExtendedForMermaid = false;
  }
};
var MarkdownService = class _MarkdownService {
  get options() {
    return this._options;
  }
  set options(value) {
    this._options = __spreadValues(__spreadValues({}, this.DEFAULT_MARKED_OPTIONS), value);
  }
  get renderer() {
    return this.options.renderer;
  }
  set renderer(value) {
    this.options.renderer = value;
  }
  constructor() {
    this.clipboardOptions = inject(CLIPBOARD_OPTIONS, {
      optional: true
    });
    this.extensions = inject(MARKED_EXTENSIONS, {
      optional: true
    });
    this.http = inject(HttpClient, {
      optional: true
    });
    this.mermaidOptions = inject(MERMAID_OPTIONS, {
      optional: true
    });
    this.platform = inject(PLATFORM_ID);
    this.sanitize = inject(SANITIZE, {
      optional: true
    });
    this.sanitizer = inject(DomSanitizer);
    this.DEFAULT_MARKED_OPTIONS = {
      renderer: new P()
    };
    this.DEFAULT_KATEX_OPTIONS = {
      delimiters: [{
        left: "$$",
        right: "$$",
        display: true
      }, {
        left: "$",
        right: "$",
        display: false
      }, {
        left: "\\(",
        right: "\\)",
        display: false
      }, {
        left: "\\begin{equation}",
        right: "\\end{equation}",
        display: true
      }, {
        left: "\\begin{align}",
        right: "\\end{align}",
        display: true
      }, {
        left: "\\begin{alignat}",
        right: "\\end{alignat}",
        display: true
      }, {
        left: "\\begin{gather}",
        right: "\\end{gather}",
        display: true
      }, {
        left: "\\begin{CD}",
        right: "\\end{CD}",
        display: true
      }, {
        left: "\\[",
        right: "\\]",
        display: true
      }]
    };
    this.DEFAULT_MERMAID_OPTIONS = {
      startOnLoad: false
    };
    this.DEFAULT_CLIPBOARD_OPTIONS = {
      buttonComponent: void 0
    };
    this.DEFAULT_PARSE_OPTIONS = {
      decodeHtml: false,
      inline: false,
      emoji: false,
      mermaid: false,
      markedOptions: void 0,
      disableSanitizer: false
    };
    this.DEFAULT_RENDER_OPTIONS = {
      clipboard: false,
      clipboardOptions: void 0,
      katex: false,
      katexOptions: void 0,
      mermaid: false,
      mermaidOptions: void 0
    };
    this.DEFAULT_SECURITY_CONTEXT = SecurityContext.HTML;
    this._options = null;
    this._reload$ = new Subject();
    this.reload$ = this._reload$.asObservable();
    this.options = inject(MARKED_OPTIONS, {
      optional: true
    });
  }
  parse(markdown, parseOptions = this.DEFAULT_PARSE_OPTIONS) {
    const {
      decodeHtml,
      inline,
      emoji,
      mermaid: mermaid2,
      disableSanitizer
    } = parseOptions;
    const markedOptions = __spreadValues(__spreadValues({}, this.options), parseOptions.markedOptions);
    const renderer = markedOptions.renderer || this.renderer || new P();
    if (this.extensions) {
      this.renderer = this.extendsRendererForExtensions(renderer);
    }
    if (mermaid2) {
      this.renderer = this.extendsRendererForMermaid(renderer);
    }
    const trimmed = this.trimIndentation(markdown);
    const decoded = decodeHtml ? this.decodeHtml(trimmed) : trimmed;
    const emojified = emoji ? this.parseEmoji(decoded) : decoded;
    const marked = this.parseMarked(emojified, markedOptions, inline);
    const sanitized = disableSanitizer ? marked : this.sanitizeHtml(marked);
    return sanitized;
  }
  render(element, options = this.DEFAULT_RENDER_OPTIONS, viewContainerRef) {
    const {
      clipboard,
      clipboardOptions,
      katex: katex2,
      katexOptions,
      mermaid: mermaid2,
      mermaidOptions
    } = options;
    if (katex2) {
      this.renderKatex(element, __spreadValues(__spreadValues({}, this.DEFAULT_KATEX_OPTIONS), katexOptions));
    }
    if (mermaid2) {
      this.renderMermaid(element, __spreadValues(__spreadValues(__spreadValues({}, this.DEFAULT_MERMAID_OPTIONS), this.mermaidOptions), mermaidOptions));
    }
    if (clipboard) {
      this.renderClipboard(element, viewContainerRef, __spreadValues(__spreadValues(__spreadValues({}, this.DEFAULT_CLIPBOARD_OPTIONS), this.clipboardOptions), clipboardOptions));
    }
    this.highlight(element);
  }
  reload() {
    this._reload$.next();
  }
  getSource(src) {
    if (!this.http) {
      throw new Error(errorSrcWithoutHttpClient);
    }
    return this.http.get(src, {
      responseType: "text"
    }).pipe(map((markdown) => this.handleExtension(src, markdown)));
  }
  highlight(element) {
    if (!isPlatformBrowser(this.platform)) {
      return;
    }
    if (typeof Prism === "undefined" || typeof Prism.highlightAllUnder === "undefined") {
      return;
    }
    if (!element) {
      element = document;
    }
    const noLanguageElements = element.querySelectorAll('pre code:not([class*="language-"])');
    Array.prototype.forEach.call(noLanguageElements, (x) => x.classList.add("language-none"));
    Prism.highlightAllUnder(element);
  }
  decodeHtml(html) {
    if (!isPlatformBrowser(this.platform)) {
      return html;
    }
    const textarea = document.createElement("textarea");
    textarea.innerHTML = html;
    return textarea.value;
  }
  extendsRendererForExtensions(renderer) {
    const extendedRenderer = renderer;
    if (extendedRenderer.ɵNgxMarkdownRendererExtendedForExtensions === true) {
      return renderer;
    }
    if (this.extensions && this.extensions.length > 0) {
      d.use(...this.extensions);
    }
    extendedRenderer.ɵNgxMarkdownRendererExtendedForExtensions = true;
    return renderer;
  }
  extendsRendererForMermaid(renderer) {
    const extendedRenderer = renderer;
    if (extendedRenderer.ɵNgxMarkdownRendererExtendedForMermaid === true) {
      return renderer;
    }
    const defaultCode = renderer.code;
    renderer.code = (token) => {
      return token.lang === "mermaid" ? `<div class="mermaid">${token.text}</div>` : defaultCode(token);
    };
    extendedRenderer.ɵNgxMarkdownRendererExtendedForMermaid = true;
    return renderer;
  }
  handleExtension(src, markdown) {
    const urlProtocolIndex = src.lastIndexOf("://");
    const urlWithoutProtocol = urlProtocolIndex > -1 ? src.substring(urlProtocolIndex + 4) : src;
    const lastSlashIndex = urlWithoutProtocol.lastIndexOf("/");
    const lastUrlSegment = lastSlashIndex > -1 ? urlWithoutProtocol.substring(lastSlashIndex + 1).split("?")[0] : "";
    const lastDotIndex = lastUrlSegment.lastIndexOf(".");
    const extension = lastDotIndex > -1 ? lastUrlSegment.substring(lastDotIndex + 1) : "";
    return !!extension && extension !== "md" ? "```" + extension + "\n" + markdown + "\n```" : markdown;
  }
  parseMarked(html, markedOptions, inline = false) {
    if (markedOptions.renderer) {
      const renderer = __spreadValues({}, markedOptions.renderer);
      delete renderer.ɵNgxMarkdownRendererExtendedForExtensions;
      delete renderer.ɵNgxMarkdownRendererExtendedForMermaid;
      delete markedOptions.renderer;
      d.use({
        renderer
      });
    }
    return inline ? d.parseInline(html, markedOptions) : d.parse(html, markedOptions);
  }
  parseEmoji(html) {
    if (!isPlatformBrowser(this.platform)) {
      return html;
    }
    if (typeof joypixels === "undefined" || typeof joypixels.shortnameToUnicode === "undefined") {
      throw new Error(errorJoyPixelsNotLoaded);
    }
    return joypixels.shortnameToUnicode(html);
  }
  renderKatex(element, options) {
    if (!isPlatformBrowser(this.platform)) {
      return;
    }
    if (typeof katex === "undefined" || typeof renderMathInElement === "undefined") {
      throw new Error(errorKatexNotLoaded);
    }
    renderMathInElement(element, options);
  }
  renderClipboard(element, viewContainerRef, options) {
    if (!isPlatformBrowser(this.platform)) {
      return;
    }
    if (typeof ClipboardJS === "undefined") {
      throw new Error(errorClipboardNotLoaded);
    }
    if (!viewContainerRef) {
      throw new Error(errorClipboardViewContainerRequired);
    }
    const {
      buttonComponent,
      buttonTemplate
    } = options;
    const preElements = element.querySelectorAll("pre");
    for (let i = 0; i < preElements.length; i++) {
      const preElement = preElements.item(i);
      const preWrapperElement = document.createElement("div");
      preWrapperElement.style.position = "relative";
      preElement.parentNode.insertBefore(preWrapperElement, preElement);
      preWrapperElement.appendChild(preElement);
      const toolbarWrapperElement = document.createElement("div");
      toolbarWrapperElement.classList.add("markdown-clipboard-toolbar");
      toolbarWrapperElement.style.position = "absolute";
      toolbarWrapperElement.style.top = ".5em";
      toolbarWrapperElement.style.right = ".5em";
      toolbarWrapperElement.style.zIndex = "1";
      preWrapperElement.insertAdjacentElement("beforeend", toolbarWrapperElement);
      preWrapperElement.onmouseenter = () => toolbarWrapperElement.classList.add("hover");
      preWrapperElement.onmouseleave = () => toolbarWrapperElement.classList.remove("hover");
      let embeddedViewRef;
      if (buttonComponent) {
        const componentRef = viewContainerRef.createComponent(buttonComponent);
        embeddedViewRef = componentRef.hostView;
        componentRef.changeDetectorRef.markForCheck();
      } else if (buttonTemplate) {
        embeddedViewRef = viewContainerRef.createEmbeddedView(buttonTemplate);
      } else {
        const componentRef = viewContainerRef.createComponent(ClipboardButtonComponent);
        embeddedViewRef = componentRef.hostView;
        componentRef.changeDetectorRef.markForCheck();
      }
      let clipboardInstance;
      embeddedViewRef.rootNodes.forEach((node) => {
        toolbarWrapperElement.appendChild(node);
        clipboardInstance = new ClipboardJS(node, {
          text: () => preElement.innerText
        });
      });
      embeddedViewRef.onDestroy(() => clipboardInstance.destroy());
    }
  }
  renderMermaid(element, options = this.DEFAULT_MERMAID_OPTIONS) {
    if (!isPlatformBrowser(this.platform)) {
      return;
    }
    if (typeof mermaid === "undefined" || typeof mermaid.initialize === "undefined") {
      throw new Error(errorMermaidNotLoaded);
    }
    const mermaidElements = element.querySelectorAll(".mermaid");
    if (mermaidElements.length === 0) {
      return;
    }
    mermaid.initialize(options);
    mermaid.run({
      nodes: mermaidElements
    });
  }
  trimIndentation(markdown) {
    if (!markdown) {
      return "";
    }
    let indentStart;
    return markdown.split("\n").map((line) => {
      let lineIdentStart = indentStart;
      if (line.length > 0) {
        lineIdentStart = isNaN(lineIdentStart) ? line.search(/\S|$/) : Math.min(line.search(/\S|$/), lineIdentStart);
      }
      if (isNaN(indentStart)) {
        indentStart = lineIdentStart;
      }
      return lineIdentStart ? line.substring(lineIdentStart) : line;
    }).join("\n");
  }
  async sanitizeHtml(html) {
    if (isSanitizeFunction(this.sanitize)) {
      return this.sanitize(await html);
    }
    if (this.sanitize !== SecurityContext.NONE) {
      return this.sanitizer.sanitize(this.sanitize ?? this.DEFAULT_SECURITY_CONTEXT, html) ?? "";
    }
    return html;
  }
  static {
    this.ɵfac = function MarkdownService_Factory(__ngFactoryType__) {
      return new (__ngFactoryType__ || _MarkdownService)();
    };
  }
  static {
    this.ɵprov = ɵɵdefineInjectable({
      token: _MarkdownService,
      factory: _MarkdownService.ɵfac
    });
  }
};
(() => {
  (typeof ngDevMode === "undefined" || ngDevMode) && setClassMetadata(MarkdownService, [{
    type: Injectable
  }], () => [], null);
})();
var PrismPlugin;
(function(PrismPlugin2) {
  PrismPlugin2["CommandLine"] = "command-line";
  PrismPlugin2["LineHighlight"] = "line-highlight";
  PrismPlugin2["LineNumbers"] = "line-numbers";
})(PrismPlugin || (PrismPlugin = {}));
var MarkdownComponent = class _MarkdownComponent {
  constructor() {
    this.element = inject(ElementRef);
    this.markdownService = inject(MarkdownService);
    this.viewContainerRef = inject(ViewContainerRef);
    this.error = new EventEmitter();
    this.load = new EventEmitter();
    this.ready = new EventEmitter();
    this._clipboard = false;
    this._commandLine = false;
    this._disableSanitizer = false;
    this._emoji = false;
    this._inline = false;
    this._katex = false;
    this._lineHighlight = false;
    this._lineNumbers = false;
    this._mermaid = false;
    this.destroyed$ = new Subject();
  }
  get disableSanitizer() {
    return this._disableSanitizer;
  }
  set disableSanitizer(value) {
    this._disableSanitizer = this.coerceBooleanProperty(value);
  }
  get inline() {
    return this._inline;
  }
  set inline(value) {
    this._inline = this.coerceBooleanProperty(value);
  }
  // Plugin - clipboard
  get clipboard() {
    return this._clipboard;
  }
  set clipboard(value) {
    this._clipboard = this.coerceBooleanProperty(value);
  }
  // Plugin - emoji
  get emoji() {
    return this._emoji;
  }
  set emoji(value) {
    this._emoji = this.coerceBooleanProperty(value);
  }
  // Plugin - katex
  get katex() {
    return this._katex;
  }
  set katex(value) {
    this._katex = this.coerceBooleanProperty(value);
  }
  // Plugin - mermaid
  get mermaid() {
    return this._mermaid;
  }
  set mermaid(value) {
    this._mermaid = this.coerceBooleanProperty(value);
  }
  // Plugin - lineHighlight
  get lineHighlight() {
    return this._lineHighlight;
  }
  set lineHighlight(value) {
    this._lineHighlight = this.coerceBooleanProperty(value);
  }
  // Plugin - lineNumbers
  get lineNumbers() {
    return this._lineNumbers;
  }
  set lineNumbers(value) {
    this._lineNumbers = this.coerceBooleanProperty(value);
  }
  // Plugin - commandLine
  get commandLine() {
    return this._commandLine;
  }
  set commandLine(value) {
    this._commandLine = this.coerceBooleanProperty(value);
  }
  ngOnChanges() {
    this.loadContent();
  }
  loadContent() {
    if (this.data != null) {
      this.handleData();
      return;
    }
    if (this.src != null) {
      this.handleSrc();
      return;
    }
  }
  ngAfterViewInit() {
    if (!this.data && !this.src) {
      this.handleTransclusion();
    }
    this.markdownService.reload$.pipe(takeUntil(this.destroyed$)).subscribe(() => this.loadContent());
  }
  ngOnDestroy() {
    this.destroyed$.next();
    this.destroyed$.complete();
  }
  async render(markdown, decodeHtml = false) {
    const parsedOptions = {
      decodeHtml,
      inline: this.inline,
      emoji: this.emoji,
      mermaid: this.mermaid,
      disableSanitizer: this.disableSanitizer
    };
    const renderOptions = {
      clipboard: this.clipboard,
      clipboardOptions: this.getClipboardOptions(),
      katex: this.katex,
      katexOptions: this.katexOptions,
      mermaid: this.mermaid,
      mermaidOptions: this.mermaidOptions
    };
    const parsed = await this.markdownService.parse(markdown, parsedOptions);
    this.element.nativeElement.innerHTML = parsed;
    this.handlePlugins();
    this.markdownService.render(this.element.nativeElement, renderOptions, this.viewContainerRef);
    this.ready.emit();
  }
  coerceBooleanProperty(value) {
    return value != null && `${String(value)}` !== "false";
  }
  getClipboardOptions() {
    if (this.clipboardButtonComponent || this.clipboardButtonTemplate) {
      return {
        buttonComponent: this.clipboardButtonComponent,
        buttonTemplate: this.clipboardButtonTemplate
      };
    }
    return void 0;
  }
  handleData() {
    this.render(this.data);
  }
  handleSrc() {
    this.markdownService.getSource(this.src).subscribe({
      next: (markdown) => {
        this.render(markdown).then(() => {
          this.load.emit(markdown);
        });
      },
      error: (error) => this.error.emit(error)
    });
  }
  handleTransclusion() {
    this.render(this.element.nativeElement.innerHTML, true);
  }
  handlePlugins() {
    if (this.commandLine) {
      this.setPluginClass(this.element.nativeElement, PrismPlugin.CommandLine);
      this.setPluginOptions(this.element.nativeElement, {
        dataFilterOutput: this.filterOutput,
        dataHost: this.host,
        dataPrompt: this.prompt,
        dataOutput: this.output,
        dataUser: this.user
      });
    }
    if (this.lineHighlight) {
      this.setPluginOptions(this.element.nativeElement, {
        dataLine: this.line,
        dataLineOffset: this.lineOffset
      });
    }
    if (this.lineNumbers) {
      this.setPluginClass(this.element.nativeElement, PrismPlugin.LineNumbers);
      this.setPluginOptions(this.element.nativeElement, {
        dataStart: this.start
      });
    }
  }
  setPluginClass(element, plugin) {
    const preElements = element.querySelectorAll("pre");
    for (let i = 0; i < preElements.length; i++) {
      const classes = plugin instanceof Array ? plugin : [plugin];
      preElements.item(i).classList.add(...classes);
    }
  }
  setPluginOptions(element, options) {
    const preElements = element.querySelectorAll("pre");
    for (let i = 0; i < preElements.length; i++) {
      Object.keys(options).forEach((option) => {
        const attributeValue = options[option];
        if (attributeValue) {
          const attributeName = this.toLispCase(option);
          preElements.item(i).setAttribute(attributeName, attributeValue.toString());
        }
      });
    }
  }
  toLispCase(value) {
    const upperChars = value.match(/([A-Z])/g);
    if (!upperChars) {
      return value;
    }
    let str = value.toString();
    for (let i = 0, n = upperChars.length; i < n; i++) {
      str = str.replace(new RegExp(upperChars[i]), "-" + upperChars[i].toLowerCase());
    }
    if (str.slice(0, 1) === "-") {
      str = str.slice(1);
    }
    return str;
  }
  static {
    this.ɵfac = function MarkdownComponent_Factory(__ngFactoryType__) {
      return new (__ngFactoryType__ || _MarkdownComponent)();
    };
  }
  static {
    this.ɵcmp = ɵɵdefineComponent({
      type: _MarkdownComponent,
      selectors: [["markdown"], ["", "markdown", ""]],
      inputs: {
        data: "data",
        src: "src",
        disableSanitizer: "disableSanitizer",
        inline: "inline",
        clipboard: "clipboard",
        clipboardButtonComponent: "clipboardButtonComponent",
        clipboardButtonTemplate: "clipboardButtonTemplate",
        emoji: "emoji",
        katex: "katex",
        katexOptions: "katexOptions",
        mermaid: "mermaid",
        mermaidOptions: "mermaidOptions",
        lineHighlight: "lineHighlight",
        line: "line",
        lineOffset: "lineOffset",
        lineNumbers: "lineNumbers",
        start: "start",
        commandLine: "commandLine",
        filterOutput: "filterOutput",
        host: "host",
        prompt: "prompt",
        output: "output",
        user: "user"
      },
      outputs: {
        error: "error",
        load: "load",
        ready: "ready"
      },
      features: [ɵɵNgOnChangesFeature],
      ngContentSelectors: _c0,
      decls: 1,
      vars: 0,
      template: function MarkdownComponent_Template(rf, ctx) {
        if (rf & 1) {
          ɵɵprojectionDef();
          ɵɵprojection(0);
        }
      },
      encapsulation: 2
    });
  }
};
(() => {
  (typeof ngDevMode === "undefined" || ngDevMode) && setClassMetadata(MarkdownComponent, [{
    type: Component,
    args: [{
      // eslint-disable-next-line @angular-eslint/component-selector
      selector: "markdown, [markdown]",
      template: "<ng-content></ng-content>"
    }]
  }], null, {
    data: [{
      type: Input
    }],
    src: [{
      type: Input
    }],
    disableSanitizer: [{
      type: Input
    }],
    inline: [{
      type: Input
    }],
    clipboard: [{
      type: Input
    }],
    clipboardButtonComponent: [{
      type: Input
    }],
    clipboardButtonTemplate: [{
      type: Input
    }],
    emoji: [{
      type: Input
    }],
    katex: [{
      type: Input
    }],
    katexOptions: [{
      type: Input
    }],
    mermaid: [{
      type: Input
    }],
    mermaidOptions: [{
      type: Input
    }],
    lineHighlight: [{
      type: Input
    }],
    line: [{
      type: Input
    }],
    lineOffset: [{
      type: Input
    }],
    lineNumbers: [{
      type: Input
    }],
    start: [{
      type: Input
    }],
    commandLine: [{
      type: Input
    }],
    filterOutput: [{
      type: Input
    }],
    host: [{
      type: Input
    }],
    prompt: [{
      type: Input
    }],
    output: [{
      type: Input
    }],
    user: [{
      type: Input
    }],
    error: [{
      type: Output
    }],
    load: [{
      type: Output
    }],
    ready: [{
      type: Output
    }]
  });
})();
var MarkdownPipe = class _MarkdownPipe {
  constructor() {
    this.domSanitizer = inject(DomSanitizer);
    this.elementRef = inject(ElementRef);
    this.markdownService = inject(MarkdownService);
    this.viewContainerRef = inject(ViewContainerRef);
    this.zone = inject(NgZone);
  }
  async transform(value, options) {
    if (value == null) {
      return "";
    }
    if (typeof value !== "string") {
      console.error(`MarkdownPipe has been invoked with an invalid value type [${typeof value}]`);
      return value;
    }
    const markdown = await this.markdownService.parse(value, options);
    this.zone.onStable.pipe(first()).subscribe(() => this.markdownService.render(this.elementRef.nativeElement, options, this.viewContainerRef));
    return this.domSanitizer.bypassSecurityTrustHtml(markdown);
  }
  static {
    this.ɵfac = function MarkdownPipe_Factory(__ngFactoryType__) {
      return new (__ngFactoryType__ || _MarkdownPipe)();
    };
  }
  static {
    this.ɵpipe = ɵɵdefinePipe({
      name: "markdown",
      type: _MarkdownPipe,
      pure: true
    });
  }
};
(() => {
  (typeof ngDevMode === "undefined" || ngDevMode) && setClassMetadata(MarkdownPipe, [{
    type: Pipe,
    args: [{
      name: "markdown"
    }]
  }], null, null);
})();
function provideMarkdown(markdownModuleConfig) {
  return [MarkdownService, markdownModuleConfig?.loader ?? [], markdownModuleConfig?.clipboardOptions ?? [], markdownModuleConfig?.markedOptions ?? [], markdownModuleConfig?.mermaidOptions ?? [], markdownModuleConfig?.markedExtensions ?? [], markdownModuleConfig?.sanitize ?? []];
}
var sharedDeclarations = [ClipboardButtonComponent, LanguagePipe, MarkdownComponent, MarkdownPipe];
var MarkdownModule = class _MarkdownModule {
  static forRoot(markdownModuleConfig) {
    return {
      ngModule: _MarkdownModule,
      providers: [provideMarkdown(markdownModuleConfig)]
    };
  }
  static forChild() {
    return {
      ngModule: _MarkdownModule
    };
  }
  static {
    this.ɵfac = function MarkdownModule_Factory(__ngFactoryType__) {
      return new (__ngFactoryType__ || _MarkdownModule)();
    };
  }
  static {
    this.ɵmod = ɵɵdefineNgModule({
      type: _MarkdownModule,
      imports: [ClipboardButtonComponent, LanguagePipe, MarkdownComponent, MarkdownPipe],
      exports: [ClipboardButtonComponent, LanguagePipe, MarkdownComponent, MarkdownPipe]
    });
  }
  static {
    this.ɵinj = ɵɵdefineInjector({});
  }
};
(() => {
  (typeof ngDevMode === "undefined" || ngDevMode) && setClassMetadata(MarkdownModule, [{
    type: NgModule,
    args: [{
      imports: sharedDeclarations,
      exports: sharedDeclarations
    }]
  }], null, null);
})();
export {
  CLIPBOARD_OPTIONS,
  ClipboardButtonComponent,
  ExtendedRenderer,
  KatexSpecificOptions,
  LanguagePipe,
  MARKED_EXTENSIONS,
  MARKED_OPTIONS,
  MERMAID_OPTIONS,
  MarkdownComponent,
  MarkdownModule,
  MarkdownPipe,
  MarkdownService,
  P as MarkedRenderer,
  PrismPlugin,
  SANITIZE,
  errorClipboardNotLoaded,
  errorClipboardViewContainerRequired,
  errorJoyPixelsNotLoaded,
  errorKatexNotLoaded,
  errorMermaidNotLoaded,
  errorSrcWithoutHttpClient,
  isSanitizeFunction,
  provideMarkdown
};
//# sourceMappingURL=ngx-markdown.js.map
