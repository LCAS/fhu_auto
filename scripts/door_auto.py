#!/usr/bin/env python

import rospy
import RPi.GPIO as GPIO
from std_msgs.msg import String

GPIO.setmode(GPIO.BCM)			#use GPIO numbers

up_gpio = 19
down_gpio = 26

doorTime = rospy.Duration(17)		#door time should be 17 seconds
pub = rospy.Publisher('status', String, queue_size=10)

# Set up GPIO and ensure relays are off
GPIO.setup(up_gpio, GPIO.OUT)
GPIO.setup(down_gpio, GPIO.OUT)
GPIO.output(up_gpio, GPIO.HIGH)
GPIO.output(down_gpio, GPIO.HIGH)

def callback(msg):
	if msg.data == 'up':
		GPIO.output(down_gpio, GPIO.HIGH)
		GPIO.output(up_gpio, GPIO.LOW)
		pub.publish('Raising the gate...')
		rospy.sleep(doorTime)
		GPIO.output(up_gpio, GPIO.HIGH)
		pub.publish('Open')

	elif msg.data == 'down':
		GPIO.output(up_gpio, GPIO.HIGH)
		GPIO.output(down_gpio, GPIO.LOW)
		pub.publish('Lowering the gate...')
		rospy.sleep(doorTime)
		GPIO.output(down_gpio, GPIO.HIGH)
		pub.publish('Closed')

	else:
		GPIO.output(down_gpio, GPIO.HIGH)
		GPIO.output(up_gpio, GPIO.HIGH)
		pub.publish('Error')

def listener():
	rospy.init_node('door')
	rospy.Subscriber('command', String, callback)
	rospy.spin()

	# Safely shutdown GPIO
	GPIO.cleanup()

if __name__ == '__main__':
	print('Running...')
	listener()
