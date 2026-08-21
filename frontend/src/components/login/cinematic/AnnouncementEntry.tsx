// SPDX-License-Identifier: Elastic-2.0
// Copyright (c) 2026 ClaymoreLab
import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { AnimatePresence, motion } from "framer-motion";
import { Megaphone, X } from "lucide-react";
import { Trans, useTranslation } from "react-i18next";
import styles from "@/components/login/login.module.css";

/**
 * 登录页顶栏的公告入口：图标 + 常驻红点，点开是公告弹窗。
 *
 * 红点不跟已读状态联动 —— 公告是拿来拦人的，看过一次就熄灭等于白挂。
 * 公告正文走 i18n（`loginCinematic.announcement.body`），换文案改翻译文件即可；
 * 译文里用 <time>…</time> 标时间窗、<hl>…</hl> 标需要强调的短句。
 */
export function AnnouncementEntry() {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!open) return;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [open]);

  return (
    <div className={styles.announcement}>
      <button
        type="button"
        className={styles.announcementTrigger}
        aria-label={t("loginCinematic.announcement.open")}
        aria-haspopup="dialog"
        onClick={() => setOpen(true)}
      >
        <Megaphone aria-hidden="true" />
        <span className={styles.announcementDot} aria-hidden="true" />
      </button>
      {createPortal(
        <AnnouncementDialog open={open} onClose={() => setOpen(false)} />,
        document.body,
      )}
    </div>
  );
}

function AnnouncementDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { t } = useTranslation();

  return (
    <AnimatePresence>
      {open ? (
        <motion.div
          className={styles.announcementOverlay}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.18, ease: "easeOut" }}
          onClick={onClose}
        >
          <motion.div
            className={styles.announcementDialog}
            role="dialog"
            aria-modal="true"
            aria-label={t("loginCinematic.announcement.title")}
            initial={{ opacity: 0, scale: 0.98, y: 10 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.98, y: 10 }}
            transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
            onClick={(event) => event.stopPropagation()}
          >
            <header className={styles.announcementHeader}>
              <Megaphone aria-hidden="true" />
              <h2 className={styles.announcementHeading}>
                {t("loginCinematic.announcement.title")}
              </h2>
              <button
                type="button"
                className={styles.announcementClose}
                aria-label={t("loginCinematic.announcement.close")}
                onClick={onClose}
              >
                <X strokeWidth={1.8} aria-hidden="true" />
              </button>
            </header>

            <div className={styles.announcementBody}>
              <p className={styles.announcementText}>
                {/* 正文里的 <time>/<hl> 由译文自己标，高亮位置跟着语序走而不是写死下标。 */}
                <Trans
                  i18nKey="loginCinematic.announcement.body"
                  components={{
                    time: <span className={styles.announcementTime} />,
                    hl: <span className={styles.announcementHighlight} />,
                  }}
                />
              </p>
            </div>

            <footer className={styles.announcementFooter}>
              <button type="button" className={styles.announcementConfirm} onClick={onClose}>
                {t("loginCinematic.announcement.confirm")}
              </button>
            </footer>
          </motion.div>
        </motion.div>
      ) : null}
    </AnimatePresence>
  );
}
