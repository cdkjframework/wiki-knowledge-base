package com.framewiki.knowledge.config;

import lombok.Data;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.context.annotation.Configuration;

/**
 * 知识库相关配置，供工具类复用。
 */
@Data
@Configuration
@ConfigurationProperties(prefix = "knowledge")
public class KnowledgeConfig {

  /**
   * 直填密钥 ID，若为空则尝试从环境变量读取。
   */
  private String secretId;

  /**
   * 直填密钥 Key，若为空则尝试从环境变量读取。
   */
  private String secretKey;

  /**
   * SecretId 环境变量名，默认使用官方推荐命名。
   */
  private String secretIdEnvKey = "TENCENTCLOUD_SECRET_ID";

  /**
   * SecretKey 环境变量名，默认使用官方推荐命名。
   */
  private String secretKeyEnvKey = "TENCENTCLOUD_SECRET_KEY";

  /**
   * 接入地域域名。
   */
  private String endpoint = "cvm.ap-shanghai.tencentcloudapi.com";

  /**
   * 区域。
   */
  private String region = "ap-shanghai";

  /**
   * HTTP 请求方法，默认 GET。
   */
  private String httpMethod = "GET";

  /**
   * 连接超时时间（秒）。
   */
  private Integer connTimeoutSeconds = 30;

  /**
   * 写入超时时间（秒）。
   */
  private Integer writeTimeoutSeconds = 30;

  /**
   * 读取超时时间（秒）。
   */
  private Integer readTimeoutSeconds = 30;

  /**
   * 是否输出 SDK 调试日志。
   */
  private boolean debug = false;

  /**
   * SDK 语言（ZH_CN 或 EN_US）。
   */
  private String language = "EN_US";
}
