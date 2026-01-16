package com.framewiki.knowledge.web;

import com.cdkjframework.core.spring.CdkjApplication;
import com.framewiki.knowledge.annotation.EnableKnowledge;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration;

/**
 * @ProjectName: knowledge-base
 * @Package: com.framewiki.knowledge.web
 * @ClassName: KnowledgeApplication
 * @Description: 本地知识库服务启动类
 * @Author: xiaLin
 * @Version: 1.0
 */
@EnableKnowledge
@SpringBootApplication(exclude = {
    DataSourceAutoConfiguration.class
})
public class KnowledgeApplication {

  /**
   * 启动方法
   *
   * @param args 启动参数
   */
  public static void main(String[] args) {
    CdkjApplication.run(KnowledgeApplication.class, args);
  }
}
