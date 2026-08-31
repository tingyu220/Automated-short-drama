import { describe, expect, it } from "vitest"
import { mount } from "@vue/test-utils"
import DramaImportDialog from "@/features/drama-import/DramaImportDialog.vue"
import type { DramaImportPreview } from "@/entities/drama-import/types"

const preview: DramaImportPreview = {
  preview_id: "preview-1",
  business_date: "2026-08-17",
  source_count: 3,
  new_count: 1,
  duplicate_count: 1,
  invalid_count: 1,
  rows: [
    {
      source_row: 4,
      drama_name: "今日新剧",
      platform: "番茄",
      available_time: "2026/8/17 10:00",
      has_validated_links: false
    }
  ],
  errors: [{ source_row: 7, message: "剧名不能为空" }]
}

describe("DramaImportDialog", () => {
  it("展示预览统计与异常，并仅在确认时发出导入事件", async () => {
    const wrapper = mount(DramaImportDialog, {
      props: { modelValue: true, preview, loading: false, error: null },
      global: {
        stubs: {
          ElDialog: { template: "<div><slot /><slot name='footer' /></div>" },
          ElTable: { template: "<div><slot /></div>" },
          ElTableColumn: true,
          "el-icon": true
        }
      }
    })

    expect(wrapper.text()).toContain("今日新剧")
    expect(wrapper.text()).toContain("重复 1")
    expect(wrapper.text()).toContain("剧名不能为空")
    await wrapper.get('[aria-label="确认导入今日剧目"]').trigger("click")

    expect(wrapper.emitted("confirm")).toEqual([[]])
  })
})
