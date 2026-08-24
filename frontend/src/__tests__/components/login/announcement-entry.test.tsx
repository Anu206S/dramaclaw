// SPDX-License-Identifier: Elastic-2.0
// Copyright (c) 2026 ClaymoreLab
import { readFileSync } from "node:fs";

import { beforeAll, describe, expect, it } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import i18next from "i18next";
import { initReactI18next } from "react-i18next";

import { AnnouncementEntry } from "@/components/login/cinematic/AnnouncementEntry";

// 用真实译文跑，而不是 mock 掉 react-i18next —— 正文里的 <time>/<hl> 标记是文案的一部分，
// 只有真 i18next 解析才能验出「高亮标签写漏了」这类改文案时最容易犯的错。
beforeAll(async () => {
  await i18next.use(initReactI18next).init({
    lng: "zh",
    resources: {
      zh: { translation: JSON.parse(readFileSync("public/locales/zh/translation.json", "utf8")) },
    },
  });
});

describe("AnnouncementEntry", () => {
  it("keeps the red dot on the trigger even after the dialog was opened", async () => {
    render(<AnnouncementEntry />);

    const trigger = screen.getByRole("button", { name: "查看公告" });
    expect(trigger.querySelector("span")).not.toBeNull();

    fireEvent.click(trigger);
    fireEvent.click(await screen.findByRole("button", { name: "我知道了" }));

    // 公告是拿来拦人的：看过一次红点也不熄。
    expect(trigger.querySelector("span")).not.toBeNull();
  });

  it("opens the announcement dialog and closes it from the confirm button", async () => {
    render(<AnnouncementEntry />);

    expect(screen.queryByRole("dialog", { name: "公告" })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "查看公告" }));

    const dialog = await screen.findByRole("dialog", { name: "公告" });
    expect(dialog).toHaveTextContent("渠道版本即将上线");

    fireEvent.click(screen.getByRole("button", { name: "我知道了" }));

    await waitFor(() =>
      expect(screen.queryByRole("dialog", { name: "公告" })).not.toBeInTheDocument(),
    );
  });

  it("renders the subject and the time window as separate highlight spans", async () => {
    render(<AnnouncementEntry />);

    fireEvent.click(screen.getByRole("button", { name: "查看公告" }));
    await screen.findByRole("dialog", { name: "公告" });

    // 高亮片段各自成元素，说明 <time>/<hl> 真的被 Trans 换成了带样式的 span，
    // 而不是当成纯文本原样打在正文里。
    expect(screen.getByText("渠道版本").tagName).toBe("SPAN");
    expect(screen.getByText("18:00-19:00").tagName).toBe("SPAN");
  });

  it("closes the dialog on Escape", async () => {
    render(<AnnouncementEntry />);

    fireEvent.click(screen.getByRole("button", { name: "查看公告" }));
    expect(await screen.findByRole("dialog", { name: "公告" })).toBeInTheDocument();

    fireEvent.keyDown(window, { key: "Escape" });

    await waitFor(() =>
      expect(screen.queryByRole("dialog", { name: "公告" })).not.toBeInTheDocument(),
    );
  });
});
