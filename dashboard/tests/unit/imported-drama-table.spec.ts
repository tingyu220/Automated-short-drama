import { mount } from "@vue/test-utils"
import ImportedDramaTable from "@/widgets/imported-drama-table/ImportedDramaTable.vue"

describe("ImportedDramaTable", () => {
  it("支持多选并只发出选中的任务", async () => {
    const wrapper = mount(ImportedDramaTable, {
      props: {
        rows: [
          {
            source_key: "one",
            task_id: "task-1",
            drama_name: "第一部",
            platform: "TOMATO",
            available_time: "2026/8/17 10:00",
            operator_name: "田雨",
            task_status: "WAITING_TIME"
          },
          {
            source_key: "two",
            task_id: "task-2",
            drama_name: "第二部",
            platform: "JUBIAN",
            available_time: "2026/8/17 12:00",
            operator_name: "田雨",
            task_status: "WAITING_TIME"
          }
        ],
        loading: false
      }
    })

    const checkboxes = wrapper.findAll('input[type="checkbox"]')
    await checkboxes[1].setValue(true)
    await wrapper.get("button").trigger("click")

    expect(wrapper.emitted("enqueue")?.[0]).toEqual([["task-1"]])
  })

  it("将未关联本地任务的导入记录标记为待关联任务", () => {
    const wrapper = mount(ImportedDramaTable, {
      props: {
        rows: [
          {
            source_key: "pending",
            task_id: null,
            drama_name: "待扫描剧",
            platform: "TOMATO",
            available_time: "2026/8/19 10:00",
            operator_name: "田雨",
            task_status: null
          }
        ],
        loading: false
      }
    })

    expect(wrapper.text()).toContain("待关联任务")
    expect(wrapper.text()).not.toContain("等待扫描")
  })
})
