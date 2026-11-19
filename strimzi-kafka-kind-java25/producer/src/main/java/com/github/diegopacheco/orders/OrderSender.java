package com.github.diegopacheco.orders;

public interface OrderSender {

    void send(Order order) throws Exception;
}
