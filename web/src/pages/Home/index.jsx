/*
Copyright (C) 2025 QuantumNous

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as
published by the Free Software Foundation, either version 3 of the
License, or (at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program. If not, see <https://www.gnu.org/licenses/>.

For commercial licensing, please contact support@quantumnous.com
*/

import React, { useContext, useEffect, useMemo, useState } from 'react';
import { Button, Typography } from '@douyinfe/semi-ui';
import { API, copy, showError, showSuccess } from '../../helpers';
import { useIsMobile } from '../../hooks/common/useIsMobile';
import { StatusContext } from '../../context/Status';
import { useActualTheme } from '../../context/Theme';
import { marked } from 'marked';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import NoticeModal from '../../components/layout/NoticeModal';
import {
  ArrowRight,
  BadgeCheck,
  Bot,
  BrainCircuit,
  Building2,
  Cable,
  ChartNoAxesCombined,
  CircleDollarSign,
  Code2,
  Copy,
  Cpu,
  ExternalLink,
  FileText,
  Lock,
  MessageSquareQuote,
  MessagesSquare,
  ReceiptText,
  Route,
  ScanSearch,
  Server,
  ShieldCheck,
  Sparkles,
  SquareTerminal,
  Wallet,
  Waypoints,
} from 'lucide-react';

const { Title, Text, Paragraph } = Typography;

const heroHighlights = [
  { icon: Building2, text: '面向中小微企业的 AI 接入基础设施' },
  { icon: ReceiptText, text: '支持对公转账、合同与发票' },
  { icon: Lock, text: '零日志，不存储用户数据' },
];

const trustMetrics = [
  { value: '100%', label: '真实模型调用' },
  { value: '99.9%', label: '目标可用性 SLA' },
  { value: '40+', label: '全球模型生态聚合' },
  { value: '1 Key', label: '统一 API 接入' },
];

const compareRows = [
  {
    dimension: '品牌归属',
    bad: '个人卖家，随时跑路失联',
    good: '小红花技术领袖俱乐部旗下，真实组织可追溯',
  },
  {
    dimension: '货源透明',
    bad: '来源不明，可能掺杂黑卡或灰产货源',
    good: '企业合同正规采购，只用可信供应链',
  },
  {
    dimension: '模型真实性',
    bad: '付 GPT 价格，实际跑廉价替代模型',
    good: '100% 真实模型调用，可查可验证',
  },
  {
    dimension: '数据安全',
    bad: '多跳转发，存在监听与篡改风险',
    good: '传输加密，零日志策略，不存储用户数据',
  },
  {
    dimension: '支付与合规',
    bad: '个人转账，无合同无发票',
    good: '支持对公转账、正式合同与合规发票',
  },
  {
    dimension: '服务支持',
    bad: '售后模糊，出现问题无人负责',
    good: '专业技术客服与企业服务专线',
  },
];

const capabilityCards = [
  {
    icon: Cable,
    title: '统一 API 接入',
    text: '一个 API Key，统一调度 GPT、Claude、Gemini、DeepSeek、Qwen 等主流模型，兼容 OpenAI 接口格式。',
  },
  {
    icon: Waypoints,
    title: '国内直连，无需魔法',
    text: '国内优化部署，低延迟接入；微信、支付宝、对公转账都可落地，适合本地团队快速上线。',
  },
  {
    icon: ShieldCheck,
    title: '企业级安全稳定',
    text: '传输加密、智能负载均衡、自动故障切换，零日志策略让 Prompt 和业务数据只留在你手里。',
  },
  {
    icon: CircleDollarSign,
    title: '按量计费，成本可控',
    text: '无月费、无最低消费，用多少付多少，以规模采购与技术优化换取合理而可持续的价格。',
  },
];

const processSteps = [
  {
    step: '01',
    title: '注册账号',
    text: '1 分钟完成企业或个人注册，立即获取测试环境。',
    icon: Building2,
  },
  {
    step: '02',
    title: '充值余额',
    text: '支持微信、支付宝、对公转账，满足团队采购流程。',
    icon: Wallet,
  },
  {
    step: '03',
    title: '生成 API Key',
    text: '一键签发统一密钥，后续模型切换无需反复改造。',
    icon: Route,
  },
  {
    step: '04',
    title: '开始调用',
    text: '兼容 OpenAI 协议，通常改一行基址配置即可接入。',
    icon: SquareTerminal,
  },
];

const audienceCards = [
  {
    title: 'AI 应用开发团队',
    text: '快速集成多模型，把精力放在业务逻辑和产品迭代上。',
  },
  {
    title: '中小企业内部工具',
    text: '客服 AI、文档处理、数据分析等场景能快速上线并控制预算。',
  },
  {
    title: '独立开发者与创业者',
    text: '低成本试错，按量计费，避免早期就背上重资产开支。',
  },
  {
    title: 'Agent / 智能体团队',
    text: '支持多模型编排和高并发调用，便于策略切换与稳定交付。',
  },
];

const modelGroups = [
  {
    name: '国际旗舰',
    models: ['GPT-5.5', 'Claude 4.7 Sonnet', 'Gemini 3.1 Pro'],
  },
  {
    name: '国产主力',
    models: ['DeepSeek 系列', 'Qwen 系列', 'GLM 系列'],
  },
  {
    name: '免费体验',
    models: ['免费模型专区', '新模型灰度试用', '低门槛验证通道'],
  },
];

const abilityTags = [
  { icon: Sparkles, label: '文本生成' },
  { icon: Code2, label: '代码生成' },
  { icon: ScanSearch, label: '多模态理解' },
  { icon: FileText, label: '长文本处理' },
  { icon: BrainCircuit, label: '推理与逻辑' },
];

const pricingCards = [
  {
    title: '免费起步',
    subtitle: '先验证，再付费',
    text: '注册即送测试额度，零风险体验模型质量、稳定性与延迟。',
  },
  {
    title: '按量付费',
    subtitle: '最适合灵活团队',
    text: '充值即用，不设月费和最低消费，适合业务波动大的团队。',
  },
  {
    title: '成长型套餐',
    subtitle: '预算更可控',
    text: '适合稳定用量的中小团队，用固定预算换取更稳的产能规划。',
  },
  {
    title: '企业定制',
    subtitle: '专属折扣与服务',
    text: '大用量场景可获得专属折扣、客服支持与配套合规服务。',
  },
];

const faqItems = [
  {
    q: '为什么 1tok 比官方便宜？',
    a: '核心来源是规模采购、统一网关与运维优化带来的成本下降，而不是依赖灰产货源或偷换模型。',
  },
  {
    q: '我的数据安全吗？',
    a: '默认采用传输加密与零日志策略，不存储你的 Prompt 和业务对话内容。',
  },
  {
    q: '支持对公转账和开发票吗？',
    a: '支持。面向企业客户可配合正式合同、对公转账和合规发票流程。',
  },
  {
    q: '和直接对接官方 API 有什么区别？',
    a: '你获得的是统一接口、多模型灵活切换、本地化支付与更低接入门槛，而不是被锁定在单一供应商。',
  },
];

const isExternalLink = (value = '') => /^https?:\/\//.test(value);

const Home = () => {
  const { t, i18n } = useTranslation();
  const [statusState] = useContext(StatusContext);
  const actualTheme = useActualTheme();
  const isMobile = useIsMobile();
  const [homePageContentLoaded, setHomePageContentLoaded] = useState(false);
  const [homePageContent, setHomePageContent] = useState('');
  const [noticeVisible, setNoticeVisible] = useState(false);

  const docsLink = statusState?.status?.docs_link || '';
  const serverAddress =
    statusState?.status?.server_address || `${window.location.origin}`;
  const enterpriseLink =
    statusState?.status?.chat_link ||
    statusState?.status?.chat_link2 ||
    docsLink ||
    '/register';
  const transparentLink = docsLink || enterpriseLink;
  const registerLink = '/register';
  const qrcodeLink = statusState?.status?.wechat_qrcode || '';
  const displayHomePageContent = async () => {
    setHomePageContent(localStorage.getItem('home_page_content') || '');
    try {
      const res = await API.get('/api/home_page_content', {
        skipErrorHandler: true,
      });
      const { success, message, data } = res.data;
      if (success) {
        let content = data;
        if (!data.startsWith('https://')) {
          content = marked.parse(data);
        }
        setHomePageContent(content);
        localStorage.setItem('home_page_content', content);

        if (data.startsWith('https://')) {
          const iframe = document.querySelector('iframe');
          if (iframe) {
            iframe.onload = () => {
              iframe.contentWindow.postMessage({ themeMode: actualTheme }, '*');
              iframe.contentWindow.postMessage({ lang: i18n.language }, '*');
            };
          }
        }
      } else {
        showError(message);
        setHomePageContent('');
      }
    } catch (error) {
      console.warn('获取首页配置失败，回退到默认落地页', error);
      setHomePageContent('');
    }
    setHomePageContentLoaded(true);
  };

  const handleCopyBaseURL = async () => {
    const ok = await copy(serverAddress);
    if (ok) {
      showSuccess(t('已复制到剪切板'));
    }
  };

  useEffect(() => {
    document.body.classList.add('landing-page-body');
    return () => {
      document.body.classList.remove('landing-page-body');
    };
  }, []);

  useEffect(() => {
    const checkNoticeAndShow = async () => {
      const lastCloseDate = localStorage.getItem('notice_close_date');
      const today = new Date().toDateString();
      if (lastCloseDate !== today) {
        try {
          const res = await API.get('/api/notice', {
            skipErrorHandler: true,
          });
          const { success, data } = res.data;
          if (success && data && data.trim() !== '') {
            setNoticeVisible(true);
          }
        } catch (error) {
          console.error('获取公告失败:', error);
        }
      }
    };

    checkNoticeAndShow();
  }, []);

  useEffect(() => {
    displayHomePageContent().then();
  }, []);

  const transparencyText = useMemo(() => {
    if (docsLink) {
      return '透明化模型信息与接入说明已开放查询';
    }
    return '状态页与透明化能力支持可由顾问协助开通';
  }, [docsLink]);

  const renderJumpButton = (
    link,
    label,
    {
      primary = false,
      icon = null,
      className = '',
      newTab = false,
    } = {},
  ) => {
    const button = (
      <Button
        theme={primary ? 'solid' : 'light'}
        type={primary ? 'primary' : 'tertiary'}
        size='large'
        icon={icon}
        className={`landing-button ${primary ? 'landing-button-primary' : 'landing-button-secondary'} ${className}`.trim()}
      >
        {label}
      </Button>
    );

    if (isExternalLink(link) || newTab) {
      return (
        <a
          href={link}
          target='_blank'
          rel='noopener noreferrer'
          className='landing-button-link'
        >
          {button}
        </a>
      );
    }

    return (
      <Link to={link} className='landing-button-link'>
        {button}
      </Link>
    );
  };

  return (
    <div className='w-full overflow-x-hidden'>
      <NoticeModal
        visible={noticeVisible}
        onClose={() => setNoticeVisible(false)}
        isMobile={isMobile}
      />
      {homePageContentLoaded && homePageContent === '' ? (
        <div className='landing-page'>
          <section className='landing-hero'>
            <div className='landing-shell landing-hero-shell'>
              <div className='landing-orb landing-orb-blue' />
              <div className='landing-orb landing-orb-amber' />
              <div className='landing-orb landing-orb-grid' />

              <div className='landing-hero-grid'>
                <div className='landing-hero-copy'>
                  <Title heading={1} className='landing-hero-title'>
                    新一代<br />品牌 Token 中转站
                  </Title>
                  <Paragraph className='landing-hero-subtitle'>
                    1tok，小红花技术领袖俱乐部旗下 AI 服务平台。聚合全球顶尖大模型，
                    为中小微企业提供稳定、安全、高性价比的一站式 API 接入。
                  </Paragraph>

                  <div className='landing-highlight-row'>
                    {heroHighlights.map(({ icon: Icon, text }) => (
                      <span className='landing-inline-pill' key={text}>
                        <Icon size={16} />
                        {text}
                      </span>
                    ))}
                  </div>

                  <div className='landing-hero-actions'>
                    {renderJumpButton(registerLink, '免费试用', {
                      primary: true,
                      icon: <ArrowRight size={18} />,
                    })}
                  </div>

                </div>

                <div className='landing-hero-trust-row'>
                  <div className='landing-card landing-story-card'>
                    <div className='landing-story-header'>
                      <img
                        src='/logo_xhh.png'
                        alt='小红花技术领袖俱乐部'
                        className='landing-story-logo'
                      />
                      <div>
                        <Text className='landing-card-label'>我们是谁</Text>
                        <Title heading={4} className='landing-card-title'>
                          小红花技术领袖俱乐部的品牌延伸
                        </Title>
                      </div>
                    </div>
                    <Paragraph className='landing-card-paragraph'>
                      小红花技术领袖俱乐部成立于 2021 年，以“为开发者全职业生涯赋能”为使命，
                      已形成全网百万级开发者影响力，并与新华网、广东省社会组织总会、粤港澳 AI 智库等机构深度合作。
                    </Paragraph>
                    {/* <Paragraph className='landing-card-paragraph'>
                      1tok 作为旗下品牌，延续“让技术人没有中年焦虑”的初心，专注把稳定、透明、可追溯的 AI 接入服务交付给中小微企业。
                    </Paragraph> */}
                    <div className='landing-bullet-grid'>
                      <div className='landing-bullet-item'>
                        <BadgeCheck size={16} />
                        有组织可追溯
                      </div>
                      <div className='landing-bullet-item'>
                        <BadgeCheck size={16} />
                        不跑路不失联
                      </div>
                      <div className='landing-bullet-item'>
                        <BadgeCheck size={16} />
                        货源透明
                      </div>
                      <div className='landing-bullet-item'>
                        <BadgeCheck size={16} />
                        无隐藏费用
                      </div>
                    </div>
                  </div>

                  <div className='landing-card landing-quote-card'>
                    <div className='landing-quote-photo-wrap'>
                      <img
                        src='/lai_picture.jpg'
                        alt='赖勇浩'
                        className='landing-quote-photo'
                      />
                      <div>
                        <Text className='landing-card-label'>创始人寄语</Text>
                        <Title heading={5} className='landing-card-title'>
                          我们卖的不是便宜，而是可持续的可靠
                        </Title>
                      </div>
                    </div>
                    <div className='landing-quote-content'>
                      <MessageSquareQuote size={22} />
                      <p>
                        我是赖勇浩。搭建 1tok 的初衷很简单: 让中小微企业能用上不打折扣、安全可靠的 AI 服务。
                        我自己就是技术人，知道稳定和透明有多重要。1tok 的每一行代码、每一笔订单，都经得起验证。
                      </p>
                    </div>
                  </div>
                </div>

                <div className='landing-hero-aside'>
                  <div className='landing-card landing-runtime-card'>
                    <div className='landing-runtime-top'>
                      <div>
                        <Text className='landing-card-label'>企业调用中枢</Text>
                        <Title heading={4} className='landing-card-title'>
                          一个入口，稳定接入全球模型
                        </Title>
                      </div>
                    </div>
                    <div className='landing-runtime-grid'>
                      <div>
                        <Server size={18} />
                        <span>统一网关</span>
                      </div>
                      <div>
                        <ShieldCheck size={18} />
                        <span>安全转发</span>
                      </div>
                      <div>
                        <Cpu size={18} />
                        <span>智能调度</span>
                      </div>
                      <div>
                        <Wallet size={18} />
                        <span>透明计费</span>
                      </div>
                    </div>
                    <div className='landing-runtime-route'>
                      <span>Client</span>
                      <ArrowRight size={15} />
                      <span>1tok Gateway</span>
                      <ArrowRight size={15} />
                      <span>GPT / Claude / Gemini</span>
                    </div>
                  </div>

                  <div className='landing-card landing-api-card'>
                    <div className='landing-card-header'>
                      <div>
                        <Text className='landing-card-label'>统一 API 地址</Text>
                        <Title heading={6} className='landing-card-title'>
                          兼容 OpenAI 协议，改一行配置即可接入
                        </Title>
                      </div>
                      <Button
                        type='tertiary'
                        theme='borderless'
                        icon={<Copy size={16} />}
                        onClick={handleCopyBaseURL}
                      >
                        复制
                      </Button>
                    </div>
                    <div className='landing-endpoint-box'>{serverAddress}</div>
                    {/* <div className='landing-api-tags'>
                      <span>GPT / Claude / Gemini / DeepSeek / Qwen</span>
                      <span>国内直连</span>
                      <span>按量付费</span>
                    </div> */}
                    <div className='landing-stats-grid'>
                      {trustMetrics.map((item) => (
                        <div className='landing-card landing-stat-card' key={item.label}>
                          <div className='landing-stat-value'>{item.value}</div>
                          <div className='landing-stat-label'>{item.label}</div>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>

              </div>
            </div>
          </section>

          <section className='landing-section'>
            <div className='landing-shell'>
              <div className='landing-section-heading'>
                <Title heading={2} className='landing-section-title'>
                  为什么值得信任
                </Title>
                <Paragraph className='landing-section-desc'>
                  1tok 不和无品牌中转站比谁更便宜，而是把中小微企业最在意的组织信用、
                  模型真实性、数据安全和交付稳定性做透。
                </Paragraph>
              </div>

              <div className='landing-card landing-compare-card'>
                {/* <div className='landing-compare-heading'>
                  <div className='landing-compare-brand'>
                    <img src='/logo_xhh.png' alt='小红花' className='landing-mini-logo' />
                    <img src='/logo_1tok.jpg' alt='1tok' className='landing-mini-logo landing-mini-logo-square' />
                    <span>为什么选择 1tok</span>
                  </div>
                  <span className='landing-compare-note'>
                    公开承诺，接受验证
                  </span>
                </div> */}
                <div className='landing-table-wrap'>
                  <table className='landing-compare-table'>
                    <thead>
                      <tr>
                        <th>维度</th>
                        <th>1tok（新一代品牌 Token 中转站）</th>
                        <th>个人 / 无品牌中转站</th>
                      </tr>
                    </thead>
                    <tbody>
                      {compareRows.map((row) => (
                        <tr key={row.dimension}>
                          <td>{row.dimension}</td>
                          <td className='landing-compare-good'>{row.good}</td>
                          <td className='landing-compare-bad'>{row.bad}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          </section>

          <section className='landing-section landing-section-alt'>
            <div className='landing-shell'>
              <div className='landing-section-heading'>
                <Title heading={2} className='landing-section-title'>
                  把 AI 接入变成一件简单、稳定、能交付的事
                </Title>
                <Paragraph className='landing-section-desc'>
                  我们把模型接入、密钥管理、故障切换和账单核对做成一条可重复交付的路径，
                  让团队少踩坑、少返工，把精力留给自己的产品。
                </Paragraph>
              </div>

              <div className='landing-card-grid landing-card-grid-four'>
                {capabilityCards.map((card) => {
                  const Icon = card.icon;
                  return (
                    <div className='landing-card landing-feature-card' key={card.title}>
                      <div className='landing-feature-icon'>
                        <Icon size={22} />
                      </div>
                      <div className='landing-feature-head'>
                        <Title heading={5} className='landing-card-title'>
                          {card.title}
                        </Title>
                        {card.badge ? (
                          <span className='landing-inline-badge'>{card.badge}</span>
                        ) : null}
                      </div>
                      <Paragraph className='landing-card-paragraph'>
                        {card.text}
                      </Paragraph>
                    </div>
                  );
                })}
              </div>

              <div className='landing-split-layout'>
                <div className='landing-card landing-process-card'>
                  <div className='landing-subheading'>
                    <Route size={18} />
                    接入流程
                  </div>
                  <div className='landing-process-grid'>
                    {processSteps.map((item) => {
                      const Icon = item.icon;
                      return (
                        <div className='landing-process-item' key={item.step}>
                          <div className='landing-process-top'>
                            <span className='landing-process-step'>{item.step}</span>
                            <img
                              src='/logo_xhh.png'
                              alt='小红花'
                              className='landing-process-logo'
                            />
                          </div>
                          <div className='landing-process-body'>
                            <div className='landing-process-icon'>
                              <Icon size={20} />
                            </div>
                            <div className='landing-process-copy'>
                              <Title heading={6} className='landing-card-title'>
                                {item.title}
                              </Title>
                              <Paragraph className='landing-card-paragraph'>
                                {item.text}
                              </Paragraph>
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>

                <div className='landing-card'>
                  <div className='landing-subheading'>
                    <Cpu size={18} />
                    适合谁用
                  </div>
                  <div className='landing-audience-list'>
                    {audienceCards.map((item) => (
                      <div className='landing-audience-item' key={item.title}>
                        <div className='landing-audience-dot' />
                        <div>
                          <Title heading={6} className='landing-card-title'>
                            {item.title}
                          </Title>
                          <Paragraph className='landing-card-paragraph'>
                            {item.text}
                          </Paragraph>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          </section>

          {/* <section className='landing-section'>
            <div className='landing-shell'>
              <div className='landing-section-heading'>
                <Title heading={2} className='landing-section-title'>
                  用覆盖度和透明度继续强化技术信任
                </Title>
              </div>

              <div className='landing-split-layout'>
                <div className='landing-card'>
                  <div className='landing-model-header'>
                    <div>
                      <Text className='landing-card-label'>模型覆盖总览</Text>
                      <Title heading={4} className='landing-card-title'>
                        全球主流模型一站式聚合
                      </Title>
                    </div>
                  </div>
                  <div className='landing-model-groups'>
                    {modelGroups.map((group) => (
                      <div className='landing-model-group' key={group.name}>
                        <div className='landing-model-group-name'>{group.name}</div>
                        <div className='landing-model-tags'>
                          {group.models.map((model) => (
                            <span className='landing-model-tag' key={model}>
                              <span className='landing-model-tag-dot' />
                              {model}
                            </span>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                  <div className='landing-model-footnote'>
                    <img src='/logo_xhh.png' alt='小红花' className='landing-mini-logo' />
                    以上模型由小红花技术团队持续维护与更新
                  </div>
                </div>

                <div className='landing-card landing-model-side-card'>
                  <div className='landing-subheading'>
                    <Bot size={18} />
                    模型能力维度
                  </div>
                  <div className='landing-ability-list'>
                    {abilityTags.map((item) => {
                      const Icon = item.icon;
                      return (
                        <div className='landing-ability-item' key={item.label}>
                          <Icon size={18} />
                          {item.label}
                        </div>
                      );
                    })}
                  </div>
                  <div className='landing-transparent-card'>
                    <div className='landing-subheading'>
                      <ChartNoAxesCombined size={18} />
                      透明化展示
                    </div>
                    <Paragraph className='landing-card-paragraph'>
                      {transparencyText}
                    </Paragraph>
                    {renderJumpButton(transparentLink, '查看状态与接入说明', {
                      icon: <ExternalLink size={16} />,
                      newTab: isExternalLink(transparentLink),
                    })}
                  </div>
                </div>
              </div>
            </div>
          </section> */}

          <section className='landing-section landing-section-alt'>
            <div className='landing-shell'>
              <div className='landing-section-heading'>
                <Title heading={2} className='landing-section-title'>
                  价格透明，不扯“全网最低价”
                </Title>
                <Paragraph className='landing-section-desc'>
                  我们承诺无隐藏费用、零日志策略和企业级服务标准。价格的目标不是夸张地低，
                  而是长期可持续地合理。
                </Paragraph>
              </div>

              {/* <div className='landing-pricing-quote'>
                <img src='/lai_picture.jpg' alt='赖勇浩' className='landing-pricing-photo' />
                <div>
                  <div className='landing-card-label'>定价原则</div>
                  <p>
                    “我们不标全网最低价，只标合理可持续的价格。因为服务你的企业，不是一锤子买卖。”
                  </p>
                </div>
              </div> */}

              <div className='landing-card-grid landing-card-grid-four'>
                {pricingCards.map((item) => (
                  <div className='landing-card landing-pricing-card' key={item.title}>
                    <Text className='landing-card-label'>{item.subtitle}</Text>
                    <Title heading={5} className='landing-card-title'>
                      {item.title}
                    </Title>
                    <Paragraph className='landing-card-paragraph'>
                      {item.text}
                    </Paragraph>
                  </div>
                ))}
              </div>

              <div className='landing-card landing-faq-card'>
                {/* <div className='landing-faq-heading'>
                  <img src='/logo_xhh.png' alt='小红花' className='landing-mini-logo' />
                  FAQ
                </div> */}
                <div className='landing-faq-list'>
                  {faqItems.map((item) => (
                    <details className='landing-faq-item' key={item.q}>
                      <summary>{item.q}</summary>
                      <p>{item.a}</p>
                    </details>
                  ))}
                </div>
              </div>
            </div>
          </section>
          {/*
          <section className='landing-section landing-cta-section'>
            <div className='landing-shell'>
              <div className='landing-card landing-cta-card'>
                <div className='landing-cta-copy'>
                  <Title heading={2} className='landing-section-title'>
                    准备开始了吗？
                  </Title>
                  <Paragraph className='landing-section-desc'>
                    注册即享测试额度，零风险体验新一代品牌中转服务。
                  </Paragraph>

                  <div className='landing-hero-actions'>
                    {renderJumpButton(registerLink, '免费注册，立即试用', {
                      primary: true,
                      icon: <ArrowRight size={18} />,
                    })}
                    {renderJumpButton(enterpriseLink, '企业咨询 / 商务合作', {
                      icon: <MessagesSquare size={18} />,
                      newTab: isExternalLink(enterpriseLink),
                    })}
                  </div>

                  <div className='landing-cta-foot'>
                    <div className='landing-cta-branding'>
                      <img src='/logo_1tok.jpg' alt='1tok' className='landing-mini-logo landing-mini-logo-square' />
                      <img src='/logo_xhh.png' alt='小红花' className='landing-mini-logo' />
                      <img src='/lai_picture.jpg' alt='赖勇浩' className='landing-mini-portrait' />
                    </div>
                    <Paragraph className='landing-card-paragraph'>
                      创始人赖勇浩与核心团队来自小红花技术领袖俱乐部。期待你的反馈，我们会和团队一起持续把服务做好。
                    </Paragraph>
                    <div className='landing-footer-links'>
                      <span>小红花技术领袖俱乐部旗下品牌</span>
                      <span>商务合作 / 企业咨询</span>
                      <span>友情链接: 小红花技术领袖俱乐部官网</span>
                    </div>
                  </div>
                </div>

                {qrcodeLink ? (
                  <div className='landing-qrcode-card'>
                    <div className='landing-card-label'>公众号 / 服务咨询</div>
                    <img src={qrcodeLink} alt='公众号二维码' className='landing-qrcode' />
                    <p>扫码关注公众号，获取最新模型上架与优惠信息</p>
                  </div>
                ) : (
                  <div className='landing-qrcode-card landing-qrcode-placeholder'>
                    <Server size={28} />
                    <Title heading={5} className='landing-card-title'>
                      企业级交付能力
                    </Title>
                    <p>为团队采购、上线验证和长期调用准备的标准化服务能力。</p>
                    <div className='landing-qrcode-features'>
                      <span>统一接口</span>
                      <span>稳定转发</span>
                      <span>透明计费</span>
                      <span>合同发票</span>
                    </div>
                  </div>
                )}
              </div>
            </div>
          </section> */}

        </div>
      ) : (
        <div className='overflow-x-hidden w-full'>
          {homePageContent.startsWith('https://') ? (
            <iframe
              src={homePageContent}
              className='w-full h-screen border-none'
            />
          ) : (
            <div
              className='mt-[60px]'
              dangerouslySetInnerHTML={{ __html: homePageContent }}
            />
          )}
        </div>
      )}
    </div>
  );
};

export default Home;