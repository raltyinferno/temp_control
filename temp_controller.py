import xlrd
import binascii
import time
import configparser
import datetime



#######################################
#Read data from config file
#######################################
config = configparser.ConfigParser()
config.read('temp_config.cfg')

print('Reading in rat set temp configurations')
rat_set_temps = {}
for option in config.options('rat_set_temps'):
    rat_set_temps[float(option)] = float(config.get('rat_set_temps', option))

print('Reading in rat maintainance temp change configurations')
rat_maint_dts = {}
for option in config.options('rat_maint_dts'):
    rat_maint_dts[float(option)] = float(config.get('rat_maint_dts', option))

print('Reading in rat warming temp change configurations')
rat_warming_dts = {}
for option in config.options('rat_warming_dts'):
    rat_warming_dts[float(option)] = float(config.get('rat_warming_dts', option))



def open_sheet(excel_file):
    workbook = xlrd.open_workbook(excel_file)
    sheet = workbook.sheet_by_index(0)
    return sheet

def read_current_temp(sheet):
    current_temp = sheet.cell_value(int(config.get('GENERAL','excel_cell_y')),int(config.get('GENERAL','excel_cell_x')))
    if current_temp ==0x2A or current_temp ==0x00:
        print('Excel sheet has an empty value in the current temp cell, this may because experiment has just started and an average temperature has not been generated yet')
        return int(config.get('MAINTENANCE','default_starting_temp'))
    else:
        print('reading in temperature of ' + str(current_temp)+ ' degrees')
        return float(current_temp)

def calculate_set_temp(temp, phase, d_temp, last_set_temp): #gets closest value from tables in temp_config
    if phase == 0:
        local_temp = rat_set_temps.get(temp, rat_set_temps[min(rat_set_temps.keys(), key=lambda k: abs(k-temp))])
        return min(40,max(4,local_temp))
    elif phase == 1:
        local_temp = rat_set_temps.get(temp, rat_set_temps[min(rat_set_temps.keys(), key=lambda k: abs(k-temp))])+rat_maint_dts.get(d_temp,rat_maint_dts[min(rat_maint_dts.keys(), key=lambda k: abs(k-d_temp))])
        return min(40,max(4,local_temp))
    elif phase == 2:
        local_temp = last_set_temp+rat_warming_dts.get(d_temp,rat_warming_dts[min(rat_warming_dts.keys(), key=lambda k: abs(k-d_temp))])
        return min(40,max(4,local_temp))
    else:
        return 0

def calculate_checksum(command): #part of generating command for temp controller
    checksum = 0
    for letter in command:
        checksum += int(ord(letter))
    return str(hex(checksum))[-2:]
        
def create_command(set_temp): #creates command to be read by 
    set_temp *= 100
    if set_temp < 0:
        set_temp = 2**16 - abs(int(set_temp))
    command = '1c'
    command += str(hex(int(set_temp)))[2:].zfill(4)
    command += calculate_checksum(command)
    return command




def write_out_file(command):
    with open('converted_command.txt','w') as out_file:
        out_file.write(command)
        out_file.close()

def write_out_temp(set_temp):
    print('writing out temperature of ' + str(set_temp)+ ' degrees')
    with open('converted_command.txt','w') as out_file:
        out_file.write(create_command(set_temp))
        out_file.close()

def main(excel_file, phase, elapsed_time,temp_prev, temp_curr, d_temp, last_set_temp):
    sheet = open_sheet(excel_file)
    current_temp = read_current_temp(sheet)
    set_temp = calculate_set_temp(current_temp,phase, d_temp, last_set_temp)
    temp_prev = temp_curr
    temp_curr = current_temp
    d_temp = temp_curr- temp_prev
    with open('experiment_log.txt','a') as out_file:
        out_file.write('elapsed time ({:02d}:{:02d}:{:02d})---Phase:{}---'.format(int(elapsed_time/(60*60)),int(elapsed_time/60)%60,elapsed_time%60,phase))
        out_file.write('Reading:'+ str(current_temp)+ '---Sending:' + str(set_temp) + '---Temp Change:'+str(d_temp)+'\n')
        out_file.close()
    write_out_temp(set_temp)
    if phase == 0 and temp_curr > float(config.get('MAINTENANCE','target'))+1:
        return 0, temp_prev, temp_curr, d_temp, set_temp
    elif phase == 0:
        print('advancing to phase 1: maintenance')
        with open('experiment_log.txt','a') as out_file:
            out_file.write('Advancing to Phase 1: Maintenance\n')
            out_file.close()
        return 1, temp_prev, temp_curr, d_temp, set_temp
    if phase == 2:
        return 2, temp_prev, temp_curr, d_temp, set_temp
    elif phase == 1 and elapsed_time >= 60*60*int(config.get('MAINTENANCE','duration')):
        print('advancing to phase 2: rewarming')
        with open('experiment_log.txt','a') as out_file:
            out_file.write('Advancing to Phase 2: Rewarming\n')
            out_file.close()
        return 2, temp_prev, temp_curr, d_temp, set_temp
    else:
        return 1, temp_prev, temp_curr, d_temp, set_temp


#########################################
################Main Loop################
#########################################
try:
    print('Begining logging')
    with open('experiment_log.txt','a') as out_file:
        out_file.write('Begining Auto Temperature Control\n')
        out_file.write('Start Time:{}\n'.format(datetime.datetime.now()))
        out_file.close()
    elapsed_time = 0
    phase = 0
    time_increment = int(config.get('GENERAL','update_frequency'))
    excel_file = config.get('GENERAL','excel_file')
    print('Reading initial temp from Excel sheet (this may take a momment)')
    temp_prev = read_current_temp(open_sheet(excel_file))
    temp_curr = temp_prev
    d_temp = 0
    set_temp = 0
    print('Begining temperature control\n')
    while True:
        print('temperature change:{}'.format(d_temp))
        phase, temp_prev, temp_curr, d_temp, set_temp= main(excel_file, phase, elapsed_time, temp_prev, temp_curr, d_temp, set_temp)
        print('elapsed time ({:02d}:{:02d}:{:02d})   Phase:{} \n'.format(int(elapsed_time/(60*60)),int(elapsed_time/60)%60,elapsed_time%60,phase))
        time.sleep(time_increment)
        elapsed_time += time_increment
except Exception as e:
    with open('experiment_log.txt','a') as out_file:
        out_file.write(repr(e)+'\n')
        out_file.close()
    print(e)

    input('press ENTER to exit. . .')