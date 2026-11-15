package com.github.diegopacheco.pipelinelag;

public interface OrderSender {

    void send(Order order) throws Exception;
}
