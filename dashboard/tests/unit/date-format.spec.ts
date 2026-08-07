import { describe, expect, it } from "vitest"
import {
  formatDateTime,
  formatDuration,
  parseDateTimeUtc
} from "@/shared/utils/format"

describe("后端 naive UTC 时间展示", () => {
  it("naive UTC 字符串按 UTC 解析并转本地时间显示", () => {
    const parsed = parseDateTimeUtc("2026-08-06T10:05:00")
    expect(parsed?.toISOString()).toBe("2026-08-06T10:05:00.000Z")
  })

  it("带空格的时间串同样按 UTC 处理", () => {
    const parsed = parseDateTimeUtc("2026-08-06 10:05:00")
    expect(parsed?.toISOString()).toBe("2026-08-06T10:05:00.000Z")
  })

  it("已带时区的时间串不重复追加 Z", () => {
    const parsed = parseDateTimeUtc("2026-08-06T10:05:00+08:00")
    expect(parsed?.toISOString()).toBe("2026-08-06T02:05:00.000Z")
  })

  it("formatDateTime 输出本地日期时间", () => {
    const tz = Intl.DateTimeFormat().resolvedOptions().timeZone
    const formatted = formatDateTime("2026-08-06T10:05:00")
    if (tz === "Asia/Shanghai") {
      expect(formatted).toBe("2026-08-06 18:05")
    } else {
      expect(formatted).toContain("2026-08-06")
    }
  })

  it("formatDuration 按 UTC 起止时间计算", () => {
    expect(
      formatDuration("2026-08-06T10:00:00", "2026-08-06T10:05:00")
    ).toBe("5m")
  })

  it("非法时间返回占位符", () => {
    expect(formatDateTime("not-a-time")).toBe("not-a-time")
    expect(formatDuration(null)).toBe("—")
  })
})
