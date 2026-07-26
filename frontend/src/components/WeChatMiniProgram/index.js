import React, { useState } from 'react';
import { Modal, Button } from 'antd';
import { WechatOutlined, ScanOutlined } from '@ant-design/icons';
import { isWeChatBrowser } from '../../utils/browserDetection';
import './index.css';

// 小程序码图片放在 public 目录下，扫码即可打开小程序
const MP_QR_SRC = '/mp-qrcode.jpg';

export default function WeChatMiniProgram({ compact = false, onNavigate }) {
  const [open, setOpen] = useState(false);
  const inWeChat = isWeChatBrowser();

  const openModal = () => {
    setOpen(true);
    if (onNavigate) onNavigate();
  };

  const trigger = compact ? (
    <div className="wxmp-drawer-entry" onClick={openModal}>
      <WechatOutlined className="wxmp-drawer-icon" />
      <span>微信小程序</span>
    </div>
  ) : (
    <Button
      type="text"
      size="small"
      icon={<WechatOutlined />}
      className="wxmp-header-btn"
      onClick={openModal}
    >
      小程序
    </Button>
  );

  return (
    <>
      {trigger}
      <Modal
        title="AI炒股指南 · 微信小程序"
        open={open}
        onCancel={() => setOpen(false)}
        footer={null}
        width={360}
        centered
      >
        <div className="wxmp-modal-body">
          <div className="wxmp-qr-wrap">
            <img
              className="wxmp-qr-img"
              src={MP_QR_SRC}
              alt="AI炒股指南小程序码"
              draggable={false}
            />
          </div>
          <div className="wxmp-tip">
            <ScanOutlined className="wxmp-tip-icon" />
            <span>微信扫一扫，随时随地看盘</span>
          </div>
          <p className="wxmp-desc">
            打开手机微信，扫描上方小程序码即可进入。行情、龙虎榜、情绪周期一手掌握。
          </p>
          {inWeChat && (
            <p className="wxmp-hint">
              检测到你在微信中打开，长按小程序码也可直接识别进入。
            </p>
          )}
        </div>
      </Modal>
    </>
  );
}
