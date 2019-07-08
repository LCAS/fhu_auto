#!/usr/bin/env python

import actionlib
import rospy
#import RPi.GPIO as GPIO
from fhu_auto.msg import door_controlAction, door_controlFeedback, door_controlResult
from std_msgs.msg import String

class ActionServer():

	def __init__(self):
		# Action Server Init
		self.action_name = "door_control_as"
		self.a_server = actionlib.SimpleActionServer(self.action_name, door_controlAction, execute_cb=self.execute_cb, auto_start=False)
		self.a_server.start()

		# R-Pi Init
		#GPIO.setmode(GPIO.BCM)			#use GPIO numbers
		up_gpio = 19
		down_gpio = 26

		# Set up GPIO and ensure relays are off
		#GPIO.setup(up_gpio, GPIO.OUT)
		#GPIO.setup(down_gpio, GPIO.OUT)
		#GPIO.output(up_gpio, GPIO.HIGH)
		#GPIO.output(down_gpio, GPIO.HIGH)

		# Variables
		self.doorTime = rospy.Duration(17)		#door time should be 17 seconds
		self.feedback = door_controlFeedback()
		self.result = door_controlResult() 

	def	timer_cb(self, event):
		print("timer triggered")
		#self.result.finished_state = 'Open'
		self.timer = True
		

	def execute_cb(self, goal):
		self.timer = False
		rate = rospy.Rate(10)

		if self.a_server.is_preempt_requested():
			rospy.loginfo('%s: Preempted' % self.action_name)
			self.success = False

		else:
			if goal.command == 'up':
				#GPIO.output(down_gpio, GPIO.HIGH)
				#GPIO.output(up_gpio, GPIO.LOW)
				rospy.Timer(self.doorTime, self.timer_cb, oneshot=True)
				while self.timer is False:
					self.feedback.status = 'Raising the gate...'
					self.a_server.publish_feedback(self.feedback)
					rate.sleep()
				#GPIO.output(up_gpio, GPIO.HIGH)
				self.result.finished_state = 'Open'
				self.success = True

			elif goal.command == 'down':
				#GPIO.output(up_gpio, GPIO.HIGH)
				#GPIO.output(down_gpio, GPIO.LOW)
				rospy.Timer(self.doorTime, self.timer_cb, oneshot=True)
				while self.timer is False:
					self.feedback.status = 'Lowering the gate...'
					self.a_server.publish_feedback(self.feedback)
					rate.sleep()
				#GPIO.output(down_gpio, GPIO.HIGH)
				self.result.finished_state = 'Closed'
				self.success = True

			else:
				#GPIO.output(down_gpio, GPIO.HIGH)
				#GPIO.output(up_gpio, GPIO.HIGH)
				self.feedback.status = 'Error'
				self.a_server.publish_feedback(self.feedback)
				self.success = False

			

		if self.success:
			self.a_server.set_succeeded(self.result)


			
if __name__ == '__main__':
	rospy.init_node("door_action_server")
	s = ActionServer()
	print('Running...')
	rospy.spin()
	# Safely shutdown GPIO
	#GPIO.cleanup()

