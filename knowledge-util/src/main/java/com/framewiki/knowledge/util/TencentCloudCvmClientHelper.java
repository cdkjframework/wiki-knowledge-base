package com.framewiki.knowledge.util;

import com.framewiki.knowledge.config.KnowledgeConfig;
import com.tencentcloudapi.common.Credential;
import com.tencentcloudapi.common.exception.TencentCloudSDKException;
import com.tencentcloudapi.common.profile.ClientProfile;
import com.tencentcloudapi.common.profile.HttpProfile;
import com.tencentcloudapi.common.profile.Language;
import com.tencentcloudapi.cvm.v20170312.CvmClient;
import com.tencentcloudapi.cvm.v20170312.models.DescribeInstancesRequest;
import com.tencentcloudapi.cvm.v20170312.models.DescribeInstancesResponse;
import com.tencentcloudapi.cvm.v20170312.models.Filter;
import com.framewiki.knowledge.constants.RequestDomainConstants;

import java.util.List;

/**
 * 封装 CVM 客户端创建与常用请求。
 */
public final class TencentCloudCvmClientHelper {

    private TencentCloudCvmClientHelper() {
    }

    /**
     * 使用默认配置并从环境变量读取密钥创建客户端。
     */
    public static CvmClient createClientFromEnv() {
        return createClient(new KnowledgeConfig());
    }

    /**
     * 基于 KnowledgeConfig 创建客户端，支持配置文件或环境变量的密钥。
     */
    public static CvmClient createClient(KnowledgeConfig config) {
        requireConfig(config);

        String secretId = firstNonBlank(config.getSecretId(), System.getenv(config.getSecretIdEnvKey()));
        String secretKey = firstNonBlank(config.getSecretKey(), System.getenv(config.getSecretKeyEnvKey()));
        if (isBlank(secretId) || isBlank(secretKey)) {
            throw new IllegalArgumentException(
                    "Tencent Cloud credentials are missing in config and environment variables.");
        }

        HttpProfile httpProfile = new HttpProfile();
        httpProfile.setReqMethod(firstNonBlank(config.getHttpMethod(), config.getHttpMethod()));
        httpProfile.setConnTimeout(safeTimeout(config.getConnTimeoutSeconds(), config.getConnTimeoutSeconds()));
        httpProfile.setWriteTimeout(safeTimeout(config.getWriteTimeoutSeconds(), config.getWriteTimeoutSeconds()));
        httpProfile.setReadTimeout(safeTimeout(config.getReadTimeoutSeconds(), config.getReadTimeoutSeconds()));
        httpProfile.setEndpoint(firstNonBlank(config.getEndpoint(), config.getEndpoint()));

        ClientProfile clientProfile = new ClientProfile();
        clientProfile.setSignMethod(ClientProfile.SIGN_TC3_256);
        clientProfile.setHttpProfile(httpProfile);
        clientProfile.setDebug(config.isDebug());
        clientProfile.setLanguage(parseLanguage(config.getLanguage()));

        Credential credential = new Credential(secretId, secretKey);
        String region = firstNonBlank(config.getRegion(), RequestDomainConstants.KNOWLEDGE_DOMAIN);
        return new CvmClient(credential, region, clientProfile);
    }

    /**
     * 按区域过滤查询实例列表。
     */
    public static DescribeInstancesResponse describeInstancesByZones(CvmClient client, List<String> zones)
            throws TencentCloudSDKException {
        if (client == null) {
            throw new IllegalArgumentException("client cannot be null");
        }

        DescribeInstancesRequest request = new DescribeInstancesRequest();
        if (zones != null && !zones.isEmpty()) {
            Filter filter = new Filter();
            filter.setName("zone");
            filter.setValues(zones.toArray(new String[0]));
            request.setFilters(new Filter[] { filter });
        }

        return client.DescribeInstances(request);
    }

    /**
     * 将响应转为 JSON 字符串，若为空则返回空串。
     */
    public static String toJson(DescribeInstancesResponse response) {
        if (response == null) {
            return "";
        }
        return DescribeInstancesResponse.toJsonString(response);
    }

    /**
     * 解析语言枚举，默认使用英文。
     */
    private static Language parseLanguage(String lang) {
        if ("ZH_CN".equalsIgnoreCase(lang)) {
            return Language.ZH_CN;
        }
        return Language.EN_US;
    }

    /**
     * 安全获取超时值，若为 null 则返回默认值。
     */
    private static int safeTimeout(Integer value, int fallback) {
        return value == null ? fallback : value;
    }

    /**
     * 返回第一个非空白字符串，若均为空则返回 null。
     */
    private static String firstNonBlank(String first, String second) {
        if (!isBlank(first)) {
            return first;
        }
        return isBlank(second) ? null : second;
    }

    /**
     * 判断字符串是否为空白。
     */
    private static boolean isBlank(String value) {
        return value == null || value.trim().isEmpty();
    }

    /**
     * 校验配置对象是否为 null。
     * 
     * @param config 配置对象
     */
    private static void requireConfig(KnowledgeConfig config) {
        if (config == null) {
            throw new IllegalArgumentException("KnowledgeConfig cannot be null");
        }
    }
}
