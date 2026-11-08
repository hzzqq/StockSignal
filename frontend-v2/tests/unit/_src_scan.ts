/**
 * 源码扫描工具：剥离注释后再做 toContain 守卫，避免「守卫被注释喂饱」式自静音。
 *
 * 历史：Python 侧守卫（批次 6 / 11）已用 stripComments + 反例自测根治同类漏洞；
 * 前端 theme-a11y / design-language 两个守卫此前读的是原始全文，toContain 会被
 * 行注释或块注释里的字符串假通过。本模块把同一套严谨性补到前端。
 *
 * 实现要点（字符级，零依赖、正确处理 JSX / 字符串）：
 *  - 字符串字面量（" ' `）内的 // 与 /* 一律按内容保留，不误删、不误当注释。
 *  - JSX 子文本（标签 > 与下一个 < 之间）内的 // 与 /* 是文本不是注释，
 *    典型坑：<div>数据来自 data/snapshots/*.json</div> 的 /*.json 不能当块注释起始。
 *  - 标签属性里的 JS 表达式 {...} / (...) 内部仍按注释处理（带括号/花括号深度跟踪）。
 */
export type ScanState = {
  inStr: '"' | "'" | '`' | null
  inJsxTag: boolean
  inJsxText: boolean
  brace: number
  paren: number
}

function newState(): ScanState {
  return { inStr: null, inJsxTag: false, inJsxText: false, brace: 0, paren: 0 }
}

/** 返回剥离注释后的源码；保留字符串字面量、JSX 文本、类型注解与 JSX 属性。 */
export function stripTsComments(src: string): string {
  const s = newState()
  let out = ''
  let i = 0
  while (i < src.length) {
    const c = src[i]
    const next = i + 1 < src.length ? src[i + 1] : ''
    const prev = i > 0 ? src[i - 1] : ''

    // 1) 字符串字面量：原样保留，内部斜杠不当注释
    if (s.inStr) {
      out += c
      if (c === s.inStr && prev !== '\\') s.inStr = null
      i++
      continue
    }
    if (c === '"' || c === "'" || c === '`') {
      s.inStr = c
      out += c
      i++
      continue
    }

    // 2) JSX 子文本：不解析注释
    if (s.inJsxText) {
      out += c
      if (c === '<') {
        s.inJsxText = false
        s.inJsxTag = true
      }
      i++
      continue
    }

    // 3) 普通代码：解析注释
    if (c === '/' && next === '/') {
      while (i < src.length && src[i] !== '\n') i++
      continue
    }
    if (c === '/' && next === '*') {
      while (i < src.length && !(src[i] === '*' && src[i + 1] === '/')) i++
      i += 2
      continue
    }
    if (c === '<' && /[a-zA-Z/]/.test(next)) {
      s.inJsxTag = true
      out += c
      i++
      continue
    }
    if (c === '{' && s.inJsxTag) {
      s.brace++
      out += c
      i++
      continue
    }
    if (c === '}' && s.inJsxTag && s.brace > 0) {
      s.brace--
      out += c
      i++
      continue
    }
    if (c === '(' && s.inJsxTag) {
      s.paren++
      out += c
      i++
      continue
    }
    if (c === ')' && s.inJsxTag && s.paren > 0) {
      s.paren--
      out += c
      i++
      continue
    }
    if (c === '>' && s.inJsxTag && s.brace === 0 && s.paren === 0) {
      s.inJsxTag = false
      s.inJsxText = true
      out += c
      i++
      continue
    }

    out += c
    i++
  }
  return out
}

/** CSS 仅含块注释（无行注释、无类型、无 JSX），用保守正则切除即可。 */
export function stripCssComments(src: string): string {
  return src.replace(/\/\*[\s\S]*?\*\//g, '')
}

/** HTML 仅含 <!-- --> 注释，单独处理，不进 TS 解析。 */
export function stripHtmlComments(src: string): string {
  return src.replace(/<!--[\s\S]*?-->/g, '')
}

/**
 * 反例自测用的「仅注释含 token」构造器：给出 token 列表，返回一段源码，
 * 其中每个 token 只出现在注释里、正文不含。守卫若在剥注释后仍 toContain 则必失败。
 */
export function commentOnlySource(tokens: string[]): string {
  const lines = tokens.map((t) => `// ${t}`)
  return [...lines, 'export const __real__ = 1', '/* ' + tokens.join(' ') + ' */'].join('\n')
}
